"""Add durable fenced jobs without changing any existing data."""
from alembic import op
import sqlalchemy as sa

revision = '008_durable_background_jobs'
down_revision = '007_missing_model_tables'
branch_labels = depends_on = None


def upgrade():
    op.create_table('background_jobs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('owner_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False), sa.Column('result', sa.JSON()),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('retry_eligible', sa.Boolean(), nullable=False),
        sa.Column('lease_token', sa.Uuid()), sa.Column('lease_expires_at', sa.DateTime(timezone=True)),
        sa.Column('worker_id', sa.String(128)), sa.Column('error_code', sa.String(80)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True)), sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('workspace_id', 'kind', 'idempotency_key', name='uq_background_job_request'))
    op.create_index('ix_background_jobs_workspace_id', 'background_jobs', ['workspace_id'])
    op.create_index('ix_background_jobs_status', 'background_jobs', ['status'])


def downgrade():
    raise RuntimeError('Forward-only: retain job evidence; no destructive downgrade')
