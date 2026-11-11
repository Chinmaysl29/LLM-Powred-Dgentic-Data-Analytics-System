"""Enforce the existing model's single-active-version invariant across all writers."""
from alembic import op
import sqlalchemy as sa

revision = '022_active_version_guard'
down_revision = '021_company_review'
branch_labels = None
depends_on = None
NAME = 'uq_dataset_active_version'
MARKER = 'created_by_022_active_version_guard'


def upgrade():
    bind = op.get_bind()
    conflicts = bind.scalar(sa.text('SELECT count(*) FROM (SELECT dataset_id FROM dataset_versions '
        'WHERE is_active GROUP BY dataset_id HAVING count(*) > 1) AS conflicts'))
    if conflicts:
        raise RuntimeError('Resolve multiple active dataset versions before migration; no records were changed')
    existing = next((i for i in sa.inspect(bind).get_indexes('dataset_versions') if i['name'] == NAME), None)
    if existing:
        predicate = str(existing.get('dialect_options', {}).get('postgresql_where', '')).lower()
        normalized = ''.join(c for c in predicate if c not in ' ()')
        if not existing['unique'] or existing['column_names'] != ['dataset_id'] or normalized not in {'is_active', 'is_active=true', 'is_activeistrue'}:
            raise RuntimeError('Existing active-version index differs from the required invariant; review it before migration')
        return
    op.create_index(NAME, 'dataset_versions', ['dataset_id'], unique=True, postgresql_where=sa.text('is_active'))
    op.execute(f"COMMENT ON INDEX {NAME} IS '{MARKER}'")


def downgrade():
    newer_artifacts = op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM dataplane_artifacts "
        "WHERE kind NOT IN ('snapshot','evidence','quality','proposal','approval','metric','connector')) "
        "OR EXISTS (SELECT 1 FROM learning_definitions WHERE governance::jsonb <> '{}'::jsonb)"))
    if newer_artifacts:
        raise RuntimeError('Archive company review artifacts before downgrade')
    # Leave a pre-existing correct index intact. Remove only this revision's index.
    created_here = op.get_bind().scalar(sa.text(
        "SELECT obj_description(to_regclass('uq_dataset_active_version'), 'pg_class')")) == MARKER
    if created_here:
        op.drop_index(NAME, table_name='dataset_versions')
