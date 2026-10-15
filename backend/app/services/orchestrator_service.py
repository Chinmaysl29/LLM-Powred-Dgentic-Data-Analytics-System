"""Orchestrator Agent Service — The CEO of all Agents.

Coordinates intent resolution, sequential agent execution, shared context management,
error recovery with partial results, and unified result aggregation.
"""

import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ValidationException
from backend.app.core.authorization import owned_dataset
from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.llm.provider import LLMProvider, get_llm_provider
from backend.app.repositories.dataset_metadata_repository import DatasetMetadataRepository
from backend.app.repositories.dataset_profile_repository import DatasetProfileRepository
from backend.app.repositories.dataset_quality_repository import DatasetQualityRepository
from backend.app.schemas.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
    WorkflowContext,
)
from backend.app.services.agent_registry import AgentRegistry
from backend.app.services.intent_classification_service import (
    IntentClassificationService,
    get_intent_classification_service,
)
from backend.app.services.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Master orchestrator coordinating agent workflows, shared context, and result aggregation."""

    def __init__(
        self,
        intent_classifier: IntentClassificationService | None = None,
        workflow_registry: WorkflowRegistry | None = None,
        agent_registry: AgentRegistry | None = None,
        planner: Any | None = None,
        llm: LLMProvider | None = None,
        db: Session | None = None,
        owner_id: str | None = None,
    ) -> None:
        self._intent_classifier = intent_classifier or IntentClassificationService(llm=llm)
        self._workflow_registry = workflow_registry or WorkflowRegistry()
        self._agent_registry = agent_registry or AgentRegistry()
        self._llm = llm
        self._db = db
        self._owner_id = owner_id
        if planner is not None:
            self._planner = planner
        else:
            from backend.app.services.workflow_planner_service import WorkflowPlannerService
            self._planner = WorkflowPlannerService(
                intent_classifier=self._intent_classifier,
                workflow_registry=self._workflow_registry,
                llm=self._llm,
            )

        if self._db:
            from backend.app.services.data_retrieval_service import DataRetrievalService
            from backend.app.services.eda_service import EDAService
            from backend.app.services.statistics_service import StatisticsService
            from backend.app.services.storage_service import StorageService
            from backend.app.core.config import get_settings
            from backend.agents.data_retrieval_agent import DataRetrievalAgentRunner
            from backend.agents.eda_agent import EDAAgentRunner
            from backend.agents.statistics_agent import StatisticsAgentRunner
            from backend.agents.validation_agent import ValidationAgentRunner
            from backend.agents.executive_summary_agent import ExecutiveSummaryAgentRunner
            from backend.app.services.validation_service import ValidationService
            from backend.app.services.executive_summary_service import ExecutiveSummaryService
            
            storage = StorageService(settings=get_settings())
            retrieval_service = DataRetrievalService(db=self._db, storage_service=storage, owner_id=self._owner_id)
            eda_service = EDAService(retrieval_service=retrieval_service)
            statistics_service = StatisticsService(retrieval_service=retrieval_service)
            validation_service = ValidationService()
            summary_service = ExecutiveSummaryService()

            from backend.agents.sql_agent import SQLAgentRunner
            from backend.agents.visualization_agent import VisualizationAgentRunner
            from backend.agents.forecasting_agent import ForecastingAgentRunner
            from backend.agents.recommendation_agent import RecommendationAgentRunner

            self._agent_registry.register(DataRetrievalAgentRunner(retrieval_service=retrieval_service))
            self._agent_registry.register(EDAAgentRunner(eda_service=eda_service, retrieval_service=retrieval_service))
            self._agent_registry.register(StatisticsAgentRunner(statistics_service=statistics_service, retrieval_service=retrieval_service))
            self._agent_registry.register(SQLAgentRunner(retrieval_service=retrieval_service))
            self._agent_registry.register(VisualizationAgentRunner(retrieval_service=retrieval_service))
            self._agent_registry.register(ForecastingAgentRunner(retrieval_service=retrieval_service))
            self._agent_registry.register(RecommendationAgentRunner())
            self._agent_registry.register(ValidationAgentRunner(validation_service=validation_service))
            self._agent_registry.register(ExecutiveSummaryAgentRunner(summary_service=summary_service, name="summary"))
            self._agent_registry.register(ExecutiveSummaryAgentRunner(summary_service=summary_service, name="executive_summary"))


    @property
    def workflow_registry(self) -> WorkflowRegistry:
        """Access the workflow registry."""
        return self._workflow_registry

    @property
    def agent_registry(self) -> AgentRegistry:
        """Access the agent registry."""
        return self._agent_registry

    async def _populate_dataset_context(self, dataset_id: str, context: WorkflowContext) -> None:
        """Enrich shared context with metadata, profile, and quality if dataset exists in database."""
        if not self._db or not dataset_id:
            return

        try:
            meta_repo = DatasetMetadataRepository(self._db)
            meta = meta_repo.get(dataset_id)
            if meta:
                context.metadata = {
                    "row_count": meta.row_count,
                    "column_count": meta.column_count,
                    "column_names": meta.column_names,
                    "column_types": meta.column_types,
                    "classifications": meta.classifications,
                }
        except Exception as exc:
            logger.debug("Could not populate metadata for dataset_id=%s: %s", dataset_id, exc)

        try:
            profile_repo = DatasetProfileRepository(self._db)
            profile = profile_repo.get(dataset_id)
            if profile:
                context.profile = {
                    "summary_statistics": profile.summary_statistics,
                    "missing_counts": profile.missing_counts,
                    "duplicate_rows": profile.duplicate_rows,
                }
        except Exception as exc:
            logger.debug("Could not populate profile for dataset_id=%s: %s", dataset_id, exc)

        try:
            quality_repo = DatasetQualityRepository(self._db)
            quality = quality_repo.get(dataset_id)
            if quality:
                context.quality = {
                    "completeness_score": quality.completeness_score,
                    "uniqueness_score": quality.uniqueness_score,
                    "overall_score": quality.overall_score,
                    "classification": quality.quality_classification,
                }
        except Exception as exc:
            logger.debug("Could not populate quality for dataset_id=%s: %s", dataset_id, exc)

    def _aggregate_results(self, context: WorkflowContext) -> tuple[dict[str, Any], str]:
        """Aggregate results across all agents into categorized domains and executive summary."""
        raw_results = context.results

        # Unified categorization
        aggregated: dict[str, Any] = {
            "analysis": raw_results.get("eda") or raw_results.get("dataset_overview") or {},
            "statistics": raw_results.get("statistics") or {},
            "forecasting": raw_results.get("forecasting") or {},
            "recommendations": raw_results.get("recommendation") or {},
            "visualization": raw_results.get("visualization") or {},
            "data_retrieval": raw_results.get("data_retrieval") or {},
            "sql": raw_results.get("sql") or {},
            "rag": raw_results.get("rag") or {},
            "quality": raw_results.get("validation") or raw_results.get("cleaning") or {},
            "raw_agent_results": raw_results,
        }

        # Determine summary
        summary_result = raw_results.get("summary")
        if isinstance(summary_result, dict) and "executive_summary" in summary_result:
            summary = summary_result["executive_summary"]
        elif isinstance(summary_result, str):
            summary = summary_result
        else:
            executed = [log.agent_name for log in context.execution_log if log.status == "success"]
            summary = (
                f"Completed workflow for '{context.query}'. "
                f"Successfully orchestrated {len(executed)} agent(s): {', '.join(executed)}."
            )

        return aggregated, summary

    async def execute(
        self,
        query: str,
        dataset_id: str | None = None,
        context: dict[str, Any] | None = None,
        max_retries: int = 1,
        dynamic_planning: bool = False,
    ) -> OrchestratorResponse:
        """Execute a user query through the full orchestration pipeline.
        
        1. Receive / Classify Intent
        2. Determine Workflow
        3. Initialize Centralized Shared Context
        4. Execute Agents Sequentially with Error Recovery
        5. Aggregate Results & Synthesize Output
        """
        start_time = time.perf_counter()

        if not query or not query.strip():
            raise ValidationException("Query cannot be empty or whitespace")
        cleaned_query = query.strip()
        if dataset_id:
            owned_dataset(self._db, dataset_id, self._owner_id)

        logger.info("Orchestrator initiated query=%s dataset_id=%s", cleaned_query[:50], dataset_id)

        # 1. Intent Classification
        explicit_intent = context.get("intent") if isinstance(context, dict) and context.get("intent") else None
        if explicit_intent:
            intent = explicit_intent
            logger.info("Using explicit intent from context: %s", intent)
        else:
            intent_res = await self._intent_classifier.classify(
                query=cleaned_query,
                context=context,
                dataset_id=dataset_id,
            )
            intent = intent_res.intent
            logger.info("Intent determined: %s (confidence: %.2f)", intent, intent_res.confidence)

        # 2. Determine Workflow
        workflow = self._workflow_registry.get_workflow(intent)
        logger.info("Workflow determined for intent=%s: %s", intent, workflow)

        # 3. Create Shared Context Object
        request_id = str(uuid4())
        shared_context = WorkflowContext(
            request_id=request_id,
            dataset_id=dataset_id,
            query=cleaned_query,
            intent=intent,
            workflow=workflow,
        )

        # Enrich context with existing dataset metadata/profile/quality if available
        if dataset_id:
            await self._populate_dataset_context(dataset_id, shared_context)

        # 3b. Dynamic Workflow Planning
        is_dynamic = dynamic_planning or (isinstance(context, dict) and context.get("dynamic_planning", False))
        if is_dynamic and self._planner:
            from backend.app.schemas.planner import WorkflowPlanningRequest
            plan_req = WorkflowPlanningRequest(
                query=cleaned_query,
                intent=intent,
                dataset_id=dataset_id,
                metadata=shared_context.metadata if shared_context.metadata else None,
                profile=shared_context.profile if shared_context.profile else None,
                quality=shared_context.quality if shared_context.quality else None,
            )
            plan = await self._planner.plan(plan_req)
            workflow = plan.steps
            shared_context.workflow = workflow
            logger.info("Dynamic workflow planned: %s", workflow)

        # 4. Sequential Agent Execution (No agent-to-agent communication)
        executed_agents: list[str] = []

        for agent_name in workflow:
            runner = self._agent_registry.get(agent_name)
            if runner is None:
                logger.warning("No runner registered for agent '%s'; recording error and continuing", agent_name)
                shared_context.add_error(agent_name, f"Unregistered agent runner: {agent_name}")
                shared_context.log_execution(agent_name=agent_name, status="skipped", duration_ms=0.0)
                continue

            # Execute runner with retry support
            agent_start = time.perf_counter()
            success = False
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    logger.debug("Executing agent: %s (attempt %d)", agent_name, attempt + 1)
                    agent_output = await runner.run(shared_context)
                    shared_context.add_result(agent_name, agent_output)
                    success = True
                    break
                except Exception as exc:
                    last_error = str(exc)
                    logger.warning("Agent '%s' attempt %d failed: %s", agent_name, attempt + 1, exc)

            agent_duration = (time.perf_counter() - agent_start) * 1000

            if success:
                executed_agents.append(agent_name)
                shared_context.log_execution(agent_name=agent_name, status="success", duration_ms=agent_duration)
                logger.info("Agent '%s' executed successfully in %.2fms", agent_name, agent_duration)
            else:
                # Agent failed — record error, preserve partial results, continue pipeline
                error_msg = f"Execution failed: {last_error}"
                shared_context.add_error(agent_name, error_msg)
                shared_context.log_execution(
                    agent_name=agent_name, status="failed", duration_ms=agent_duration, error=error_msg
                )
                logger.error("Agent '%s' failed after retries: %s; continuing workflow", agent_name, last_error)

        # 5. Result Aggregation & Output Generation
        aggregated_results, executive_summary = self._aggregate_results(shared_context)
        total_duration = (time.perf_counter() - start_time) * 1000

        # Determine overall status
        if len(shared_context.errors) == 0:
            status = "success"
        elif len(executed_agents) > 0:
            status = "partial_success"
        else:
            status = "failed"

        logger.info(
            "Orchestrator completed request_id=%s status=%s executed=%d errors=%d duration=%.2fms",
            request_id,
            status,
            len(executed_agents),
            len(shared_context.errors),
            total_duration,
        )

        return OrchestratorResponse(
            request_id=request_id,
            dataset_id=dataset_id,
            query=cleaned_query,
            intent=intent,
            status=status,
            workflow=workflow,
            executed_agents=executed_agents,
            summary=executive_summary,
            results=aggregated_results,
            errors=shared_context.errors,
            execution_time_ms=round(total_duration, 2),
        )


def get_orchestrator_service(
    intent_service: IntentClassificationService = Depends(get_intent_classification_service),
    db: Session = Depends(get_db_session),
    current_user: Any = Depends(get_current_user),
) -> OrchestratorService:
    """FastAPI dependency provider yielding an OrchestratorService instance."""
    try:
        llm = get_llm_provider()
    except Exception:
        llm = None

    return OrchestratorService(
        intent_classifier=intent_service,
        llm=llm,
        db=db,
        owner_id=str(current_user.id),
    )
