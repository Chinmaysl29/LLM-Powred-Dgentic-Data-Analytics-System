"""Continuous Improvement Master Orchestrator (Phase 11.10).

Central intelligence for enterprise SaaS platform evolution.
Integrates:
1. Feedback Intelligence (11.1)
2. Product Analytics (11.2)
3. Model Evaluation (11.3)
4. AI Quality Monitoring (11.4)
5. A/B Testing Platform (11.5)
6. Feature Flag System (11.6)
7. Cost Optimization Engine (11.7)
8. Continuous Learning Pipeline (11.8)

Responsibilities:
- Computes composite platform_health (0 to 100)
- Synthesizes prioritized improvement_plan roadmap
- Generates optimization recommendations & risk alerts
- Provides structured logging & end-to-end integration
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from backend.operations.ab_testing import ABTestingPlatform, ab_testing_platform
from backend.operations.ai_quality_monitor import AIQualityMonitor, ai_quality_monitor
from backend.operations.continuous_learning import ContinuousLearningPipeline, continuous_learning_pipeline
from backend.operations.cost_optimizer import CostOptimizationEngine, cost_optimization_engine
from backend.operations.feedback_intelligence import UserFeedbackIntelligence, feedback_intelligence
from backend.operations.feature_flags import FeatureFlagSystem, feature_flag_system
from backend.operations.model_evaluation import ModelEvaluationFramework, model_evaluation_framework
from backend.operations.product_analytics import ProductAnalyticsEngine, product_analytics

logger = logging.getLogger(__name__)


@dataclass
class ImprovementPlanTask:
    task_id: str
    area: str
    action: str
    priority: str
    expected_impact: str
    source_subsystem: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ContinuousImprovementOrchestrator:
    """Master Orchestrator coordinating continuous post-launch optimization."""

    def __init__(
        self,
        feedback: UserFeedbackIntelligence = feedback_intelligence,
        analytics: ProductAnalyticsEngine = product_analytics,
        model_eval: ModelEvaluationFramework = model_evaluation_framework,
        quality: AIQualityMonitor = ai_quality_monitor,
        ab_testing: ABTestingPlatform = ab_testing_platform,
        feature_flags: FeatureFlagSystem = feature_flag_system,
        cost_optimizer: CostOptimizationEngine = cost_optimization_engine,
        learning: ContinuousLearningPipeline = continuous_learning_pipeline,
    ) -> None:
        self.feedback = feedback
        self.analytics = analytics
        self.model_eval = model_eval
        self.quality = quality
        self.ab_testing = ab_testing
        self.feature_flags = feature_flags
        self.cost_optimizer = cost_optimizer
        self.learning = learning

    def calculate_platform_health(self) -> float:
        """Compute composite platform health score (0 to 100).
        
        Weights:
        - Quality & Hallucination Score: 35%
        - Budget & Cost Efficiency: 25%
        - Model Evaluation Baseline: 20%
        - User Sentiment / Absence of Critical Feedback: 20%
        """
        # Quality sub-score (0-100)
        quality_score = self.quality.compute_quality_score()

        # Cost sub-score (100 if budget < 80%, linearly drops to 0 if > 150%)
        cost_data = self.cost_optimizer.get_cost_analysis()
        budget_pct = cost_data.get("budget_utilized_percent", 0.0)
        if budget_pct <= 80.0:
            cost_score = 100.0
        elif budget_pct >= 150.0:
            cost_score = 30.0
        else:
            cost_score = max(0.0, 100.0 - (budget_pct - 80.0) * 1.0)

        # Feedback sub-score
        fb_data = self.feedback.generate_feedback_analytics()
        crit_count = fb_data.get("critical_unresolved_count", 0)
        feedback_score = max(0.0, 100.0 - (crit_count * 15.0))

        # Model evaluation sub-score
        reports = self.model_eval.get_all_reports()
        if reports:
            all_accuracies = [
                r["accuracy"] for r_list in reports.values() for r in r_list if "accuracy" in r
            ]
            eval_score = (sum(all_accuracies) / len(all_accuracies)) * 100.0 if all_accuracies else 100.0
        else:
            eval_score = 100.0

        composite = (
            (quality_score * 0.35)
            + (cost_score * 0.25)
            + (eval_score * 0.20)
            + (feedback_score * 0.20)
        )
        return round(max(0.0, min(100.0, composite)), 1)

    def generate_orchestration_cycle(self) -> Dict[str, Any]:
        """Execute full platform continuous improvement loop."""
        logger.info("Executing Phase 11 Continuous Improvement Orchestration cycle.")
        health = self.calculate_platform_health()

        improvement_plan: List[Dict[str, Any]] = []
        risk_alerts: List[str] = []

        # 1. Harvest feedback signals
        fb_data = self.feedback.generate_feedback_analytics()
        if fb_data.get("critical_unresolved_count", 0) > 0:
            count = fb_data["critical_unresolved_count"]
            risk_alerts.append(f"{count} unresolved critical customer feedback tickets need triage.")
            improvement_plan.append(ImprovementPlanTask(
                task_id=f"ROADMAP_FB_{len(improvement_plan) + 1}",
                area="User Experience & Reliability",
                action="Triage and remediate critical customer tickets",
                priority="CRITICAL",
                expected_impact="Reduces churn and resolves severe blocker bugs",
                source_subsystem="feedback_intelligence",
            ).to_dict())

        # 2. Harvest cost optimization signals
        cost_data = self.cost_optimizer.get_cost_analysis()
        for rec in cost_data.get("recommendations", []):
            if rec.get("id") != "REC_HEALTHY_SPEND":
                improvement_plan.append(ImprovementPlanTask(
                    task_id=f"ROADMAP_COST_{len(improvement_plan) + 1}",
                    area="Cloud & AI Unit Economics",
                    action=rec["title"],
                    priority=rec["urgency"],
                    expected_impact=f"Projected savings: ${rec.get('potential_savings_usd', 0.0):.2f}/mo",
                    source_subsystem="cost_optimizer",
                ).to_dict())

        # 3. Harvest continuous learning signals
        learn_data = self.learning.get_improvements()
        for act in learn_data.get("improvement_actions", []):
            if act.get("target") != "platform_wide":
                improvement_plan.append(ImprovementPlanTask(
                    task_id=f"ROADMAP_LEARN_{len(improvement_plan) + 1}",
                    area="Autonomous Agent Quality",
                    action=act["description"],
                    priority=act["priority"],
                    expected_impact="Eliminates recurring query corrections and elevates prediction accuracy",
                    source_subsystem="continuous_learning",
                ).to_dict())

        # 4. Harvest quality monitoring alerts
        quality_data = self.quality.get_status()
        if quality_data.get("has_active_alerts"):
            for alt in quality_data.get("alerts", []):
                risk_alerts.append(f"Quality SLA Alert on {alt['component']}: {alt['message']}")

        # Baseline plan task if all is green
        if not improvement_plan:
            improvement_plan.append(ImprovementPlanTask(
                task_id="ROADMAP_BASE_01",
                area="Platform Growth",
                action="Maintain standard operational parameters and expand automated A/B model trials",
                priority="LOW",
                expected_impact="Ensures platform performance remains state of the art",
                source_subsystem="orchestrator",
            ).to_dict())

        status_text = "EXCELLENT" if health >= 90.0 else ("DEGRADED" if health >= 75.0 else "CRITICAL")

        return {
            "platform_health": health,
            "status": status_text,
            "improvement_plan": improvement_plan,
            "risk_alerts": risk_alerts,
            "total_roadmap_tasks": len(improvement_plan),
            "orchestrated_at": datetime.now(timezone.utc).isoformat(),
        }


continuous_improvement_orchestrator = ContinuousImprovementOrchestrator()
