"""Workflow Planner Service for AI Data Analyst OS.

Dynamically creates, optimizes, and dependency-orders custom agent execution plans
based on dataset metadata, profile statistics, data quality metrics, and composite user goals.
"""

import logging
import re
from typing import Any
from uuid import uuid4

from fastapi import Depends

from backend.app.core.exceptions import ValidationException
from backend.app.core.security import get_current_user
from backend.app.learning import failure_memory
from backend.app.learning.memory_contract import merge_steps
from backend.app.llm.provider import LLMProvider, get_llm_provider
from backend.app.schemas.planner import (
    PlanDependency,
    WorkflowPlan,
    WorkflowPlanningRequest,
)
from backend.app.services.intent_classification_service import (
    IntentClassificationService,
    get_intent_classification_service,
)
from backend.app.services.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)

# Canonical prerequisite dependencies for specialized agents
AGENT_DEPENDENCY_GRAPH: dict[str, list[str]] = {
    "data_retrieval": [],
    "eda": ["data_retrieval"],
    "statistics": ["data_retrieval"],
    "forecasting": ["data_retrieval", "statistics"],
    "visualization": ["data_retrieval"],
    "correlation": ["data_retrieval", "statistics"],
    "recommendation": ["data_retrieval"],
    "sql": ["data_retrieval"],
    "rag": ["data_retrieval"],
    "validation": ["data_retrieval"],
    "cleaning": ["data_retrieval", "validation"],
    "summary": ["data_retrieval"],
}


class DependencyEngine:
    """Manages prerequisite resolution, dependency tracking, and topological agent ordering."""

    def __init__(self, graph: dict[str, list[str]] | None = None) -> None:
        self._graph = graph or AGENT_DEPENDENCY_GRAPH

    def get_prerequisites(self, step: str) -> list[str]:
        """Return declared prerequisites for a step."""
        return list(self._graph.get(step, ["data_retrieval"] if step != "data_retrieval" else []))

    def resolve_and_order(self, steps: list[str]) -> list[str]:
        """Ensure all required prerequisites exist and are sorted in valid topological execution order."""
        resolved: set[str] = set()

        def add_with_prereqs(step_name: str) -> None:
            for prereq in self.get_prerequisites(step_name):
                if prereq not in resolved:
                    add_with_prereqs(prereq)
            resolved.add(step_name)

        for step in steps:
            add_with_prereqs(step)

        # Standard deterministic stage weights to preserve logical pipeline flow:
        # data_retrieval -> validation -> cleaning -> eda -> correlation -> statistics -> forecasting -> recommendation -> visualization -> sql/rag -> summary
        stage_weights = {
            "data_retrieval": 10,
            "validation": 20,
            "cleaning": 30,
            "eda": 40,
            "correlation": 45,
            "statistics": 50,
            "forecasting": 60,
            "recommendation": 70,
            "visualization": 80,
            "sql": 85,
            "rag": 85,
            "summary": 100,
        }

        sorted_steps = sorted(
            resolved,
            key=lambda s: (stage_weights.get(s, 75), steps.index(s) if s in steps else 99),
        )
        return sorted_steps

    def build_dependencies(self, steps: list[str]) -> list[PlanDependency]:
        """Build dependency declarations for the output plan."""
        dependencies: list[PlanDependency] = []
        for step in steps:
            prereqs = [p for p in self.get_prerequisites(step) if p in steps]
            dependencies.append(PlanDependency(step=step, requires=prereqs))
        return dependencies


class RulesEngine:
    """Applies contextual heuristic rules based on metadata, quality, and composite user queries."""

    def evaluate(
        self,
        query: str,
        intent: str,
        initial_steps: list[str],
        metadata: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        quality: dict[str, Any] | None = None,
        dataset_type: str | None = None,
    ) -> tuple[list[str], list[str], list[str], bool]:
        """Apply business, data shape, and composite goal rules.
        
        Returns:
            Tuple of (modified_steps, rules_triggered, optimizations_applied, use_sampling)
        """
        steps = list(initial_steps)
        rules_triggered: list[str] = []
        optimizations: list[str] = []
        use_sampling = False

        normalized_query = query.lower()

        # Rule 1: Composite Goal Analysis (e.g. "Analyze my sales dataset and predict next quarter revenue")
        has_analysis_request = bool(re.search(r"\b(analyze|analysis|eda|overview|explore)\b", normalized_query))
        has_prediction_request = bool(re.search(r"\b(predict|prediction|forecast|forecasting|future revenue|next quarter)\b", normalized_query))

        if has_analysis_request and has_prediction_request:
            if "eda" not in steps:
                steps.append("eda")
            if "forecasting" not in steps:
                steps.append("forecasting")
            rules_triggered.append("Composite goal detected: Synthesized exploratory analysis and forecasting.")

        # Rule 2: Revenue Drivers / Driver Analysis (e.g. "Find revenue drivers")
        if re.search(r"\b(drivers?|revenue drivers?|key factors?|influencers?)\b", normalized_query):
            if "eda" not in steps:
                steps.append("eda")
            if "correlation" not in steps:
                steps.append("correlation")
            if "recommendation" not in steps:
                steps.append("recommendation")
            rules_triggered.append("Driver analysis requested: Injected eda, correlation, and recommendation steps.")

        # Rule 3: Temporal / Time-Series Guard for Forecasting
        if "forecasting" in steps and metadata:
            column_names = [c.lower() for c in metadata.get("column_names", [])]
            col_types = {str(k).lower(): str(v).lower() for k, v in metadata.get("column_types", {}).items()}
            datetime_cols = metadata.get("classifications", {}).get("datetime", [])

            has_datetime = (
                len(datetime_cols) > 0
                or any(re.search(r"(date|time|timestamp|year|month|day)", c) for c in column_names)
                or any("date" in t or "time" in t for t in col_types.values())
            )

            # If metadata was explicitly populated with columns, but none are temporal:
            if len(column_names) > 0 and not has_datetime:
                steps.remove("forecasting")
                if "eda" not in steps:
                    steps.append("eda")
                rules_triggered.append("No datetime columns detected in metadata: Removed forecasting step and fallen back to EDA.")

        # Rule 4: Data Quality Remediation Guard
        if quality:
            overall_score = float(quality.get("overall_score", 100.0))
            if overall_score < 60.0:
                if "validation" not in steps:
                    steps.append("validation")
                if "cleaning" not in steps:
                    steps.append("cleaning")
                rules_triggered.append(f"Low quality score ({overall_score:.1f} < 60.0): Injected data quality validation and cleaning steps.")

        # Rule 5: Large Dataset Sampling Optimization
        if metadata:
            row_count = int(metadata.get("row_count", 0))
            if row_count > 1_000_000:
                use_sampling = True
                optimizations.append("Applied dataset sampling optimization for large dataset (>1M rows).")

        return steps, rules_triggered, optimizations, use_sampling


class OptimizationLayer:
    """Optimizes execution steps by eliminating redundancies and computing duration estimates."""

    @staticmethod
    def deduplicate(steps: list[str]) -> list[str]:
        """Remove duplicate steps while preserving order."""
        seen = set()
        deduped = []
        for s in steps:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        return deduped

    @staticmethod
    def estimate_execution_time(steps: list[str], row_count: int = 0, use_sampling: bool = False) -> float:
        """Calculate estimated total execution duration in seconds."""
        base_step_durations = {
            "data_retrieval": 0.5,
            "validation": 0.4,
            "cleaning": 0.8,
            "eda": 1.2,
            "correlation": 0.9,
            "statistics": 0.8,
            "forecasting": 1.5,
            "recommendation": 0.7,
            "visualization": 0.6,
            "sql": 0.5,
            "rag": 0.8,
            "summary": 1.0,
        }
        total = sum(base_step_durations.get(s, 0.5) for s in steps)
        if row_count > 1_000_000 and not use_sampling:
            total *= 2.5
        return round(total, 1)


class WorkflowPlannerService:
    """Master Workflow Planning Service generating optimized, dependency-verified execution plans."""

    def __init__(
        self,
        intent_classifier: IntentClassificationService | None = None,
        workflow_registry: WorkflowRegistry | None = None,
        llm: LLMProvider | None = None,
        owner_id: str | None = None,
    ) -> None:
        self._intent_classifier = intent_classifier or IntentClassificationService(llm=llm)
        self._workflow_registry = workflow_registry or WorkflowRegistry()
        self._dependency_engine = DependencyEngine()
        self._rules_engine = RulesEngine()
        self._optimization_layer = OptimizationLayer()
        self._llm = llm
        self._owner_id = owner_id

    @property
    def workflow_registry(self) -> WorkflowRegistry:
        return self._workflow_registry

    async def plan(self, request: WorkflowPlanningRequest) -> WorkflowPlan:
        """Analyze request context, evaluate dynamic rules, and generate an execution plan."""
        if not request.query or not request.query.strip():
            raise ValidationException("Query cannot be empty or whitespace")
        cleaned_query = request.query.strip()

        # 1. Resolve Intent
        intent = request.intent
        if not intent:
            intent_res = await self._intent_classifier.classify(
                query=cleaned_query,
                dataset_id=request.dataset_id,
            )
            intent = intent_res.intent
        logger.info("Workflow planning initiated for intent=%s query=%s", intent, cleaned_query[:50])

        # 2. Get Baseline Workflow Template
        base_template = self._workflow_registry.get_workflow(intent)
        memory_applied = False
        try:
            hints = await failure_memory.recall(self._owner_id, request.dataset_id, cleaned_query, intent)
            augmented = merge_steps(base_template, hints, intent)
            memory_applied = augmented != base_template
            base_template = augmented
        except Exception:
            pass  # A memory failure must not change the original planner path.

        # 3. Apply Contextual Rules Engine
        (
            modified_steps,
            rules_triggered,
            optimizations,
            use_sampling,
        ) = self._rules_engine.evaluate(
            query=cleaned_query,
            intent=intent,
            initial_steps=base_template,
            metadata=request.metadata,
            profile=request.profile,
            quality=request.quality,
            dataset_type=request.dataset_type,
        )
        if memory_applied:
            rules_triggered.append("Added analytical checks from a reviewed past failure.")

        # 4. Resolve Prerequisites and Dependency Graph Ordering
        ordered_steps = self._dependency_engine.resolve_and_order(modified_steps)

        # 5. Optimization (Deduplication and Performance Tuning)
        final_steps = self._optimization_layer.deduplicate(ordered_steps)

        row_count = int(request.metadata.get("row_count", 0)) if request.metadata else 0
        estimated_time = self._optimization_layer.estimate_execution_time(
            final_steps, row_count=row_count, use_sampling=use_sampling
        )

        dependencies = self._dependency_engine.build_dependencies(final_steps)

        workflow_type = "dynamic" if rules_triggered or optimizations else "template"
        plan_id = f"wf_{uuid4().hex[:8]}"

        logger.info(
            "Workflow plan generated plan_id=%s type=%s steps=%s rules=%d",
            plan_id,
            workflow_type,
            final_steps,
            len(rules_triggered),
        )

        return WorkflowPlan(
            workflow_id=plan_id,
            intent=intent,
            workflow_type=workflow_type,
            steps=final_steps,
            dependencies=dependencies,
            estimated_execution_time=estimated_time,
            optimizations_applied=optimizations,
            rules_triggered=rules_triggered,
            use_sampling=use_sampling,
        )


def get_workflow_planner_service(
    intent_service: IntentClassificationService = Depends(get_intent_classification_service),
    current_user: Any = Depends(get_current_user),
) -> WorkflowPlannerService:
    """FastAPI dependency yielding WorkflowPlannerService instance."""
    try:
        llm = get_llm_provider()
    except Exception:
        llm = None
    return WorkflowPlannerService(
        intent_classifier=intent_service,
        llm=llm,
        owner_id=str(current_user.id) if getattr(current_user, "id", None) else None,
    )
