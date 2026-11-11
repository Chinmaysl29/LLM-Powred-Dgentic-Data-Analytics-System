"""Add resolver audit only; existing tables and policies remain unchanged."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '017_column_resolver'
down_revision = '016_failure_memory'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('resolver_events',
        sa.Column('id', sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid, sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('workspace_id', sa.Uuid, sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('actor_id', sa.Uuid, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reviewer_id', sa.Uuid, sa.ForeignKey('users.id')),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.dataset_id'), nullable=False),
        sa.Column('dataset_version', sa.Integer, nullable=False),
        sa.Column('schema_hash', sa.String(64), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('previous_version', sa.Integer, nullable=False),
        sa.Column('model_digest', sa.String(64)),
        sa.Column('runtime_digest', sa.String(64), nullable=False),
        sa.Column('detail', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('version >= 0 AND previous_version >= 0 AND dataset_version > 0', name='ck_resolver_versions'),
        sa.CheckConstraint("action IN ('stage','shadow','promote','rollback','disable')", name='ck_resolver_action'))
    for column in ('workspace_id', 'actor_id', 'reviewer_id', 'dataset_id'):
        op.create_index(f'ix_resolver_events_{column}', 'resolver_events', [column])
    op.create_index('ix_resolver_events_tenant_version', 'resolver_events', ['tenant_id', 'version', 'action'])
    op.execute('ALTER TABLE resolver_events ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE resolver_events FORCE ROW LEVEL SECURITY')
    predicate = """tenant_id::text=current_setting('app.tenant_id',true)
        AND workspace_id::text=current_setting('app.workspace_id',true)
        AND actor_id::text=current_setting('app.actor_id',true)
        AND EXISTS (
          SELECT 1 FROM workspaces w JOIN tenants t ON t.id=w.tenant_id AND t.tenant_status='active'
          JOIN tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
          JOIN users u ON u.id=tm.user_id AND u.is_active
          JOIN workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
          WHERE w.id=resolver_events.workspace_id AND w.tenant_id=resolver_events.tenant_id
          AND w.status='active' AND u.id=resolver_events.actor_id
          AND tm.role IN ('viewer','analyst','admin','owner')
          AND (tm.role IN ('owner','admin') OR wm.role IN ('viewer','analyst','admin','owner')))
        AND EXISTS (
          SELECT 1 FROM datasets d JOIN dataset_workspace_bindings b ON b.dataset_id=d.dataset_id
          WHERE d.dataset_id=resolver_events.dataset_id AND b.workspace_id=resolver_events.workspace_id
          AND d.owner_id=current_setting('app.actor_id',true) AND d.status NOT IN ('deleted','archived','purged'))"""
    op.execute(f'CREATE POLICY resolver_read ON resolver_events FOR SELECT USING ({predicate})')
    op.execute(f"CREATE POLICY resolver_shadow_insert ON resolver_events FOR INSERT WITH CHECK ({predicate} AND action='shadow' AND reviewer_id IS NULL)")


def downgrade():
    op.drop_table('resolver_events')
