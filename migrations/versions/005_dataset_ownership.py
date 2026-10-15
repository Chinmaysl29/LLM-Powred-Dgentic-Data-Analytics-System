"""Quarantine legacy datasets and enable verified ownership for new uploads."""
from alembic import op
import sqlalchemy as sa

revision = "005_dataset_ownership"
down_revision = "004_phase17_canonical_dataset_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("owner_id", sa.String(36), nullable=True))
    op.create_index("ix_datasets_owner_id", "datasets", ["owner_id"])
    # Deliberately no backfill: assignment requires an explicit owner decision.


def downgrade() -> None:
    raise RuntimeError("Ownership downgrade requires an explicit data-access recovery plan")
