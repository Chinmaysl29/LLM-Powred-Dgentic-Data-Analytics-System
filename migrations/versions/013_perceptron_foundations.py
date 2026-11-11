"""Optional failure evidence and versioned learner storage; new tables only."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "013_perceptron_foundations"
down_revision = "012_adaptive_skills"
branch_labels = None
depends_on = None


def evidence_columns():
    return [
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.Uuid, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("dataset_schema_hash", sa.String(64)), sa.Column("question", sa.Text),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("features", JSONB, nullable=False), sa.Column("predicted", sa.String(80)),
        sa.Column("truth", sa.String(80)), sa.Column("signal_type", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade():
    op.create_table("learner_weights",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.Uuid, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("learner", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer, nullable=False), sa.Column("weights", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("tenant_id", "learner", "version", name="uq_learner_version"),
        sa.CheckConstraint("version > 0", name="ck_learner_version_positive"))
    op.create_index("uq_learner_active", "learner_weights", ["tenant_id", "learner"],
                    unique=True, postgresql_where=sa.text("is_active IS TRUE"))
    op.create_table("feedback_events", *evidence_columns())
    op.create_table("mistakes", *evidence_columns(),
        sa.Column("error_type", sa.String(80), nullable=False), sa.Column("corrected_plan", JSONB))
    for name in ("learner_weights", "feedback_events", "mistakes"):
        op.create_index(f"ix_{name}_tenant_created", name, ["tenant_id", "created_at"])
        predicate = f"""tenant_id::text=current_setting('app.tenant_id',true) AND EXISTS (
          SELECT 1 FROM tenant_memberships tm JOIN tenants t ON t.id=tm.tenant_id
          JOIN users u ON u.id=tm.user_id
          WHERE tm.tenant_id={name}.tenant_id AND tm.active AND t.tenant_status='active'
          AND u.is_active AND u.id::text=current_setting('app.actor_id',true)
          AND tm.role IN ('viewer','analyst','admin','owner'))"""
        if name != "learner_weights":
            for column in ("workspace_id", "actor_id"):
                op.create_index(f"ix_{name}_{column}", name, [column])
            predicate += f""" AND workspace_id::text=current_setting('app.workspace_id',true)
              AND EXISTS (SELECT 1 FROM workspaces w
                JOIN tenant_memberships tm ON tm.tenant_id=w.tenant_id AND tm.active
                LEFT JOIN workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=tm.user_id AND wm.active
                WHERE w.id={name}.workspace_id AND w.tenant_id={name}.tenant_id AND w.status='active'
                AND tm.user_id::text=current_setting('app.actor_id',true)
                AND (tm.role IN ('owner','admin') OR wm.role IN ('viewer','analyst','admin','owner')))"""
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY perceptron_read ON {name} FOR SELECT USING ({predicate})")
        if name == "feedback_events":
            op.execute(f"""CREATE POLICY perceptron_insert ON {name} FOR INSERT WITH CHECK (
                {predicate} AND actor_id::text=current_setting('app.actor_id',true)
                AND truth IS NULL AND question IS NULL AND signal_type='hard_failure')""")
        # Weights/mistakes have no runtime write policy until their later phases.


def downgrade():
    for name in ("mistakes", "feedback_events", "learner_weights"):
        op.drop_table(name)
