"""Review and revocation links; only a new table, existing policies unchanged."""
from alembic import op
import sqlalchemy as sa

revision = "016_failure_memory"
down_revision = "015_router_releases"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("failure_memory_links",
        sa.Column("mistake_id", sa.Uuid, sa.ForeignKey("mistakes.id"), primary_key=True),
        sa.Column("feedback_id", sa.Uuid, sa.ForeignKey("feedback_events.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewer_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("dataset_version", sa.Integer, nullable=False),
        sa.Column("schema_hash", sa.String(64), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.Uuid, sa.ForeignKey("users.id")),
        sa.UniqueConstraint("feedback_id", name="uq_failure_memory_feedback"),
        sa.CheckConstraint("dataset_version > 0", name="ck_failure_memory_version"))
    for column in ("workspace_id", "actor_id", "reviewer_id", "dataset_id", "revoked_by"):
        op.create_index(f"ix_failure_memory_links_{column}", "failure_memory_links", [column])
    op.create_index("ix_failure_memory_scope", "failure_memory_links", ["tenant_id", "actor_id", "dataset_id", "dataset_version"])
    op.execute("ALTER TABLE failure_memory_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE failure_memory_links FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY failure_memory_read ON failure_memory_links FOR SELECT USING (
      tenant_id::text=current_setting('app.tenant_id',true)
      AND workspace_id::text=current_setting('app.workspace_id',true)
      AND actor_id::text=current_setting('app.actor_id',true)
      AND EXISTS (
        SELECT 1 FROM workspaces w JOIN tenants t ON t.id=w.tenant_id AND t.tenant_status='active'
        JOIN tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
        JOIN users u ON u.id=tm.user_id AND u.is_active
        LEFT JOIN workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
        WHERE w.id=failure_memory_links.workspace_id AND w.tenant_id=failure_memory_links.tenant_id
        AND w.status='active' AND u.id=failure_memory_links.actor_id
        AND tm.role IN ('viewer','analyst','admin','owner')
        AND (tm.role IN ('owner','admin') OR wm.role IN ('viewer','analyst','admin','owner')))
      AND EXISTS (
        SELECT 1 FROM datasets d JOIN dataset_workspace_bindings b ON b.dataset_id=d.dataset_id
        WHERE d.dataset_id=failure_memory_links.dataset_id AND b.workspace_id=failure_memory_links.workspace_id
        AND d.owner_id=current_setting('app.actor_id',true) AND d.status NOT IN ('deleted','archived','purged')))
    """)
    # Reviewed corrections are managed only by the privileged operator CLI.


def downgrade():
    op.drop_table("failure_memory_links")
