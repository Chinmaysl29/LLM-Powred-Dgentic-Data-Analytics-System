"""Persist seven-stage runs and bounded evidence; additive only."""
from alembic import op
from backend.app.models.analysis_run import AnalysisRun, AnalysisStage, AnalysisArtifact, AnalysisEvent
revision = '009_analysis_runs'
down_revision = '008_durable_background_jobs'
branch_labels = depends_on = None

def upgrade():
    for model in (AnalysisRun, AnalysisStage, AnalysisArtifact, AnalysisEvent):
        model.__table__.create(op.get_bind())

def downgrade():
    raise RuntimeError('Forward-only: preserve analysis evidence')
