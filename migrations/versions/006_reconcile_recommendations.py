"""Reconcile the verified legacy recommendation table name without copying data.

Revision ID: 006_reconcile_recommendations
Revises: 005_dataset_ownership
"""
from alembic import op
import sqlalchemy as sa

revision = "006_reconcile_recommendations"
down_revision = "005_dataset_ownership"
branch_labels = None
depends_on = None

REQUIRED = {
    'recommendation_id', 'dataset_id', 'version_id', 'version_number',
    'recommendation_type', 'severity', 'priority_score', 'status', 'column_name',
    'description', 'suggested_action', 'estimated_quality_gain',
    'algorithm_metadata', 'prerequisites', 'created_at', 'resolved_at', 'created_by',
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    canonical, legacy = 'cleaning_recommendations', 'dataset_recommendations'
    if canonical in tables and legacy in tables:
        raise RuntimeError('Both recommendation tables exist; explicit reconciliation is required')
    source = canonical if canonical in tables else legacy if legacy in tables else None
    if source is None:
        raise RuntimeError('Recommendation storage is missing; restore or review schema before upgrading')
    if {c['name'] for c in inspector.get_columns(source)} != REQUIRED:
        raise RuntimeError('Recommendation columns differ from the verified migration contract')
    if inspector.get_pk_constraint(source)['constrained_columns'] != ['recommendation_id']:
        raise RuntimeError('Recommendation primary key differs from the contract')
    relations = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns'])) for f in inspector.get_foreign_keys(source)}
    if not { (('dataset_id',), 'datasets', ('dataset_id',)), (('version_id',), 'dataset_versions', ('version_id',)) } <= relations:
        raise RuntimeError('Recommendation ownership foreign keys are missing')
    indexes = {tuple(i['column_names']) for i in inspector.get_indexes(source)}
    if not {('dataset_id', 'version_id'), ('dataset_id', 'status'), ('priority_score',)} <= indexes:
        raise RuntimeError('Recommendation lookup indexes are missing')
    if not any(c['name'] == 'chk_priority_score_range' for c in inspector.get_check_constraints(source)):
        raise RuntimeError('Recommendation priority constraint is missing')
    if source == legacy:
        op.rename_table(legacy, canonical)


def downgrade() -> None:
    # A clean installation already had the canonical name before this revision.
    # Renaming blindly would break that installation and existing application code.
    raise RuntimeError('Schema reconciliation is forward-only; restore from a verified backup for rollback')
