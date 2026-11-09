"""ORM model registry — import all models so Alembic and Base.metadata discover them."""

from backend.app.models.base import Base, TimestampMixin
from backend.app.models.user import User
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_metadata import DatasetMetadata
from backend.app.models.dataset_profile import DatasetProfile
from backend.app.models.dataset_quality import DatasetQuality
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.dataset_recommendation import DatasetRecommendation
from backend.app.models.conversation import Conversation, Message
from backend.app.models.analysis import Analysis
from backend.app.models.forecast_run import ForecastRun
from backend.app.models.tenant import Tenant
from backend.app.models.workspace import Workspace
from backend.app.models.department import Department
from backend.app.models.team import Team
from backend.app.models.project import Project
from backend.app.models.collaboration import (
    Comment,
    Mention,
    Activity,
    Task,
    TaskStatus,
    TaskPriority,
    Notification,
    NotificationType,
    NotificationChannel,
)
from backend.app.models.connector import (
    ConnectorRecord,
    ConnectorType,
    ConnectorStatus,
)
from backend.app.models.audit_entry import AuditEntry
from backend.app.models.audit_log import AuditLog

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "Dataset",
    "DatasetMetadata",
    "DatasetProfile",
    "DatasetQuality",
    "DatasetVersion",
    "DatasetRecommendation",
    "Conversation",
    "Message",
    "Analysis",
    "ForecastRun",
    "Tenant",
    "Workspace",
    "Department",
    "Team",
    "Project",
    "Comment",
    "Mention",
    "Activity",
    "Task",
    "TaskStatus",
    "TaskPriority",
    "Notification",
    "NotificationType",
    "NotificationChannel",
    "ConnectorRecord",
    "ConnectorType",
    "ConnectorStatus",
    "AuditEntry",
    "AuditLog",
]
from backend.app.models.background_job import DurableJob
from backend.app.models.analysis_run import AnalysisRun, AnalysisStage, AnalysisArtifact, AnalysisEvent
from backend.app.models.learning import TABLES as LEARNING_TABLES
from backend.app.models.adaptive import TABLES as ADAPTIVE_TABLES
from backend.app.learning.tables import learner_weights, feedback_events, mistakes
from backend.app.learning.shadow_table import shadow_predictions
from backend.app.learning.release_table import router_releases
from backend.app.learning.memory_table import failure_memory_links
from backend.app.learning.column_table import resolver_events
from backend.app.learning.selection_table import selection_events
