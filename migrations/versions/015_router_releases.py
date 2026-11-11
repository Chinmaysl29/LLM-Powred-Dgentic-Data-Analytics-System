"""Add operator release history; no changes to existing table schemas or policies."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "015_router_releases"
down_revision = "014_perceptron_shadow"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("router_releases",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("previous_version", sa.Integer, nullable=False),
        sa.Column("model_digest", sa.String(64)),
        sa.Column("runtime_digest", sa.String(64), nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("version >= 0 AND previous_version >= 0", name="ck_router_release_versions"),
        sa.CheckConstraint("action IN ('stage','promote','rollback','disable')", name="ck_router_release_action"))
    op.create_index("ix_router_releases_tenant_id", "router_releases", ["tenant_id", "id"])
    op.create_index("ix_router_releases_actor_id", "router_releases", ["actor_id"])
    op.execute("ALTER TABLE router_releases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE router_releases FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY router_release_read ON router_releases FOR SELECT USING (
      tenant_id::text=current_setting('app.tenant_id',true) AND EXISTS (
        SELECT 1 FROM tenant_memberships tm JOIN tenants t ON t.id=tm.tenant_id
        JOIN users u ON u.id=tm.user_id
        WHERE tm.tenant_id=router_releases.tenant_id AND tm.active
        AND t.tenant_status='active' AND u.is_active
        AND u.id::text=current_setting('app.actor_id',true)
        AND tm.role IN ('viewer','analyst','admin','owner')))""")
    # No runtime INSERT/UPDATE/DELETE policy. The explicit operator CLI requires
    # a privileged DB connection and an active tenant owner/admin identity.


def downgrade():
    op.drop_table("router_releases")
