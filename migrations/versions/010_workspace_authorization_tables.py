"""Create workspace authorization tables.

Promotes the reviewed SQL from migrations/proposed/workspace_authorization.sql
into the Alembic revision chain. Additive only — no legacy rows are modified.

These tables are required by backend.app.core.workspace_authorization and by
the CI tests (test_authenticated_dataset_isolation.py).

Revision ID: 010_workspace_authorization_tables
Revises: 009_analysis_runs
"""

from alembic import op
import sqlalchemy as sa

revision = "010_workspace_authorization_tables"
down_revision = "009_analysis_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())

    # ── tenant_memberships ────────────────────────────────────────────────────
    if "tenant_memberships" not in existing:
        op.create_table(
            "tenant_memberships",
            sa.Column(
                "tenant_id",
                sa.UUID(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.UUID(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "role",
                sa.String(20),
                nullable=False,
                server_default="analyst",
            ),
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.CheckConstraint(
                "role IN ('owner', 'admin', 'analyst', 'viewer')",
                name="ck_tenant_memberships_role",
            ),
        )
        op.create_index(
            "ix_tenant_memberships_user",
            "tenant_memberships",
            ["user_id"],
        )

    # ── workspace_memberships ─────────────────────────────────────────────────
    if "workspace_memberships" not in existing:
        op.create_table(
            "workspace_memberships",
            sa.Column(
                "workspace_id",
                sa.UUID(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.UUID(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "role",
                sa.String(20),
                nullable=False,
                server_default="analyst",
            ),
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.CheckConstraint(
                "role IN ('owner', 'admin', 'analyst', 'viewer')",
                name="ck_workspace_memberships_role",
            ),
        )
        op.create_index(
            "ix_workspace_memberships_user",
            "workspace_memberships",
            ["user_id"],
        )

    # ── dataset_workspace_bindings ────────────────────────────────────────────
    if "dataset_workspace_bindings" not in existing:
        op.create_table(
            "dataset_workspace_bindings",
            sa.Column(
                "dataset_id",
                sa.String(36),
                sa.ForeignKey("datasets.dataset_id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                sa.UUID(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_dataset_workspace_bindings_workspace",
            "dataset_workspace_bindings",
            ["workspace_id"],
        )


def downgrade() -> None:
    # Additive tables; downgrade drops them in reverse dependency order.
    # Only safe in a development or isolated CI environment.
    op.drop_table("dataset_workspace_bindings")
    op.drop_table("workspace_memberships")
    op.drop_table("tenant_memberships")
