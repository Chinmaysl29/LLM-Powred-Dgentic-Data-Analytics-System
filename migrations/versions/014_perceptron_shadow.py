"""Append-only scoped shadow observations; no changes to existing tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "014_perceptron_shadow"
down_revision = "013_perceptron_foundations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("shadow_predictions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.Uuid, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("dataset_version", sa.Integer, nullable=False),
        sa.Column("dataset_schema_hash", sa.String(64)),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("feature_version", sa.String(64), nullable=False),
        sa.Column("features", JSONB, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("live_route", sa.String(20), nullable=False),
        sa.Column("live_intent", sa.String(80)), sa.Column("live_operation", sa.String(30)),
        sa.Column("shadow_intent", sa.String(80), nullable=False),
        sa.Column("candidate_intent", sa.String(80), nullable=False),
        sa.Column("margin", sa.Float, nullable=False),
        sa.Column("abstained", sa.Boolean, nullable=False),
        sa.Column("model_source", sa.String(30), nullable=False),
        sa.Column("model_version", sa.Integer), sa.Column("rejected_version", sa.Integer),
        sa.Column("model_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("dataset_version > 0", name="ck_shadow_dataset_version"),
        sa.CheckConstraint("margin >= 0 AND margin < 'Infinity'::float8", name="ck_shadow_finite_margin"))
    op.create_index("ix_shadow_predictions_tenant_created", "shadow_predictions", ["tenant_id", "created_at"])
    for column in ("workspace_id", "actor_id", "dataset_id"):
        op.create_index(f"ix_shadow_predictions_{column}", "shadow_predictions", [column])
    op.execute("ALTER TABLE shadow_predictions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE shadow_predictions FORCE ROW LEVEL SECURITY")
    predicate = """tenant_id::text=current_setting('app.tenant_id',true)
      AND workspace_id::text=current_setting('app.workspace_id',true)
      AND EXISTS (
        SELECT 1 FROM workspaces w JOIN tenants t ON t.id=w.tenant_id AND t.tenant_status='active'
        JOIN tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
        JOIN users u ON u.id=tm.user_id AND u.is_active
        LEFT JOIN workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
        WHERE w.id=shadow_predictions.workspace_id AND w.tenant_id=shadow_predictions.tenant_id
        AND w.status='active' AND u.id::text=current_setting('app.actor_id',true)
        AND tm.role IN ('viewer','analyst','admin','owner')
        AND (tm.role IN ('owner','admin') OR wm.role IN ('viewer','analyst','admin','owner')))
      AND EXISTS (
        SELECT 1 FROM datasets d JOIN dataset_workspace_bindings b ON b.dataset_id=d.dataset_id
        WHERE d.dataset_id=shadow_predictions.dataset_id AND b.workspace_id=shadow_predictions.workspace_id
        AND d.owner_id=current_setting('app.actor_id',true) AND d.status NOT IN ('deleted','archived','purged'))"""
    op.execute(f"CREATE POLICY shadow_read ON shadow_predictions FOR SELECT USING ({predicate})")
    op.execute(f"""CREATE POLICY shadow_insert ON shadow_predictions FOR INSERT WITH CHECK (
        {predicate} AND actor_id::text=current_setting('app.actor_id',true))""")
    # No runtime UPDATE/DELETE policy. Observation is not a teacher label.


def downgrade():
    op.drop_table("shadow_predictions")
