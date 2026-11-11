"""Verified supervisor evidence, immutable revisions and scoped authority.

Revision ID: 011_verified_learning
Revises: 010_workspace_authorization_tables
"""
from alembic import op
import sqlalchemy as sa

revision = '011_verified_learning'
down_revision = '010_workspace_authorization_tables'
branch_labels = None
depends_on = None


def upgrade():
    # This published revision owns a frozen copy of the table definitions below.
    from pathlib import Path
    op.get_bind().exec_driver_sql((Path(__file__).parents[1] / 'learning_schema_v1.sql').read_text())
    for name in TABLE_NAMES:
        op.execute(sa.text(f'ALTER TABLE {name} ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE {name} FORCE ROW LEVEL SECURITY'))
        predicate = """workspace_id::text = current_setting('app.workspace_id', true)
          AND EXISTS (SELECT 1 FROM workspaces w
            JOIN tenants t ON t.id=w.tenant_id AND t.tenant_status='active'
            JOIN tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
            JOIN users u ON u.id=tm.user_id AND u.is_active
            LEFT JOIN workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
            WHERE w.id={table_name}.workspace_id AND w.status='active'
              AND u.id::text=current_setting('app.actor_id', true)
              AND tm.role IN ('viewer','analyst','admin','owner')
              AND (tm.role IN ('admin','owner') OR wm.role IN ('viewer','analyst','admin','owner')))""".format(table_name=name)
        op.execute(sa.text(f'CREATE POLICY learning_scope ON {name} USING ({predicate}) WITH CHECK ({predicate})'))
    # Append-only evidence, protected even from accidental ORM updates by app roles.
    op.execute("""CREATE FUNCTION learning_immutable_v1() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Immutable learning evidence'; END; $$""")
    for name in IMMUTABLE:
        op.execute(f'CREATE TRIGGER immutable_revision BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION learning_immutable_v1()')
    op.execute("""CREATE FUNCTION learning_definition_immutable_v1() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable definition version'; END IF;
        IF OLD.content::text IS DISTINCT FROM NEW.content::text OR OLD.content_hash IS DISTINCT FROM NEW.content_hash
          OR OLD.key IS DISTINCT FROM NEW.key OR OLD.version IS DISTINCT FROM NEW.version
          OR OLD.workspace_id IS DISTINCT FROM NEW.workspace_id OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
          OR OLD.created_at IS DISTINCT FROM NEW.created_at OR (NOT OLD.active AND NEW.active)
        THEN RAISE EXCEPTION 'Immutable definition version'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute('CREATE TRIGGER immutable_definition BEFORE UPDATE OR DELETE ON learning_definitions FOR EACH ROW EXECUTE FUNCTION learning_definition_immutable_v1()')


TABLE_NAMES = ['learning_runs', 'learning_attempts', 'learning_feedback', 'learning_lessons',
               'learning_revisions', 'learning_verifications', 'learning_definitions',
               'learning_cases', 'learning_bundles', 'learning_evaluations',
               'learning_controls', 'learning_audit']
IMMUTABLE = ['learning_revisions', 'learning_verifications', 'learning_cases', 'learning_bundles', 'learning_audit']


def downgrade():
    for name in reversed(TABLE_NAMES):
        op.drop_table(name)
    op.execute('DROP FUNCTION learning_immutable_v1()')
    op.execute('DROP FUNCTION IF EXISTS learning_definition_immutable_v1()')
