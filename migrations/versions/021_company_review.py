"""Extend existing definition and immutable artifact stores for company review."""
from alembic import op
import sqlalchemy as sa

revision = '021_company_review'
down_revision = '020_auth_token_revocations'
branch_labels = None
depends_on = None

OLD = "'snapshot','evidence','quality','proposal','approval','metric','connector'"
NEW = OLD + ",'policy','workflow','review','schedule','incident','comparison','version_change'"


def upgrade():
    op.add_column('learning_definitions', sa.Column('governance', sa.JSON(), nullable=False,
                                                  server_default=sa.text("'{}'")))
    op.execute("""CREATE OR REPLACE FUNCTION learning_definition_immutable_v1() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable definition version'; END IF;
        IF OLD.id IS DISTINCT FROM NEW.id OR OLD.content::text IS DISTINCT FROM NEW.content::text
          OR OLD.content_hash IS DISTINCT FROM NEW.content_hash OR OLD.key IS DISTINCT FROM NEW.key
          OR OLD.version IS DISTINCT FROM NEW.version OR OLD.workspace_id IS DISTINCT FROM NEW.workspace_id
          OR OLD.actor_id IS DISTINCT FROM NEW.actor_id OR OLD.created_at IS DISTINCT FROM NEW.created_at
          OR (OLD.governance->'spec')::text IS DISTINCT FROM (NEW.governance->'spec')::text
          OR (OLD.governance->>'spec_hash') IS DISTINCT FROM (NEW.governance->>'spec_hash')
          OR (NOT OLD.active AND NEW.active AND NOT COALESCE(
             OLD.governance->>'status'='review' AND NEW.governance->>'status'='approved', FALSE))
        THEN RAISE EXCEPTION 'Immutable definition version'; END IF;
        RETURN NEW;
      END; $$""")
    op.drop_constraint('ck_dataplane_kind', 'dataplane_artifacts', type_='check')
    op.create_check_constraint('ck_dataplane_kind', 'dataplane_artifacts', f'kind IN ({NEW})')
    op.drop_constraint('ck_dataplane_dataset', 'dataplane_artifacts', type_='check')
    op.create_check_constraint('ck_dataplane_dataset', 'dataplane_artifacts',
        "kind IN ('connector','policy') OR dataset_id IS NOT NULL")
    # Existing scope and insert-only RLS policies apply to every new artifact kind.
    op.create_index('ix_dataplane_parent_kind', 'dataplane_artifacts', ['parent_id', 'kind', 'created_at'])


def downgrade():
    # Refuse a lossy downgrade. Feature rollback does not require schema rollback.
    op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM dataplane_artifacts WHERE kind NOT IN ({OLD})) "
               "OR EXISTS (SELECT 1 FROM learning_definitions WHERE governance::jsonb <> '{}'::jsonb) "
               "THEN RAISE EXCEPTION 'Archive company review artifacts and governed definitions before downgrade'; END IF; END $$")
    op.drop_index('ix_dataplane_parent_kind', table_name='dataplane_artifacts')
    op.drop_constraint('ck_dataplane_kind', 'dataplane_artifacts', type_='check')
    op.create_check_constraint('ck_dataplane_kind', 'dataplane_artifacts', f'kind IN ({OLD})')
    op.drop_constraint('ck_dataplane_dataset', 'dataplane_artifacts', type_='check')
    op.create_check_constraint('ck_dataplane_dataset', 'dataplane_artifacts', "kind='connector' OR dataset_id IS NOT NULL")
    op.execute("""CREATE OR REPLACE FUNCTION learning_definition_immutable_v1() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable definition version'; END IF;
        IF OLD.content::text IS DISTINCT FROM NEW.content::text OR OLD.content_hash IS DISTINCT FROM NEW.content_hash
          OR OLD.key IS DISTINCT FROM NEW.key OR OLD.version IS DISTINCT FROM NEW.version
          OR OLD.workspace_id IS DISTINCT FROM NEW.workspace_id OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
          OR OLD.created_at IS DISTINCT FROM NEW.created_at OR (NOT OLD.active AND NEW.active)
        THEN RAISE EXCEPTION 'Immutable definition version'; END IF;
        RETURN NEW;
      END; $$""")
    op.drop_column('learning_definitions', 'governance')
