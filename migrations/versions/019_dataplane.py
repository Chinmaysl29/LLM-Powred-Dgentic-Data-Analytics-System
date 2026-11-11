"""Add immutable dataplane metadata; reuse existing durable jobs and dataset versions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "019_dataplane"
down_revision = "018_selection_policies"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("dataplane_artifacts",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.Uuid, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.dataset_id")),
        sa.Column("job_id", sa.Uuid, sa.ForeignKey("background_jobs.id")),
        sa.Column("parent_id", sa.Uuid, sa.ForeignKey("dataplane_artifacts.id")),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("job_id", name="uq_dataplane_job_publication"),
        sa.CheckConstraint("kind IN ('snapshot','evidence','quality','proposal','approval','metric','connector')",
                           name="ck_dataplane_kind"),
        sa.CheckConstraint("kind='connector' OR dataset_id IS NOT NULL", name="ck_dataplane_dataset"))
    op.create_index("ix_dataplane_scope", "dataplane_artifacts", ["tenant_id", "workspace_id", "actor_id", "kind", "created_at"])
    for column in ("workspace_id", "actor_id", "dataset_id", "parent_id"):
        op.create_index("ix_dataplane_" + column, "dataplane_artifacts", [column])
    op.execute("ALTER TABLE dataplane_artifacts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dataplane_artifacts FORCE ROW LEVEL SECURITY")
    predicate = """tenant_id::text=current_setting('app.tenant_id',true)
        AND workspace_id::text=current_setting('app.workspace_id',true)
        AND actor_id::text=current_setting('app.actor_id',true)
        AND EXISTS (SELECT 1 FROM workspaces w
            JOIN tenants t ON t.id=w.tenant_id AND t.tenant_status='active'
            JOIN tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
            JOIN users u ON u.id=tm.user_id AND u.is_active
            LEFT JOIN workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
            WHERE w.id=dataplane_artifacts.workspace_id AND w.tenant_id=dataplane_artifacts.tenant_id
            AND w.status='active' AND u.id=dataplane_artifacts.actor_id
            AND tm.role IN ('viewer','analyst','admin','owner')
            AND (tm.role IN ('owner','admin') OR wm.role IN ('viewer','analyst','admin','owner')))
        AND (dataset_id IS NULL OR EXISTS (SELECT 1 FROM datasets d
            JOIN dataset_workspace_bindings b ON b.dataset_id=d.dataset_id
            WHERE d.dataset_id=dataplane_artifacts.dataset_id
            AND b.workspace_id=dataplane_artifacts.workspace_id
            AND d.owner_id=current_setting('app.actor_id',true)
            AND d.status NOT IN ('deleted','archived','purged')))"""
    op.execute(f"CREATE POLICY dataplane_read ON dataplane_artifacts FOR SELECT USING ({predicate})")
    writer = """EXISTS (SELECT 1 FROM tenant_memberships tm
        LEFT JOIN workspace_memberships wm ON wm.user_id=tm.user_id AND wm.workspace_id=dataplane_artifacts.workspace_id AND wm.active
        WHERE tm.tenant_id=dataplane_artifacts.tenant_id AND tm.user_id=dataplane_artifacts.actor_id AND tm.active
        AND (tm.role IN ('admin','owner') OR (tm.role='analyst' AND wm.role IN ('analyst','admin','owner'))))"""
    op.execute(f"CREATE POLICY dataplane_insert ON dataplane_artifacts FOR INSERT WITH CHECK ({predicate} AND {writer})")


def downgrade():
    op.drop_table("dataplane_artifacts")
