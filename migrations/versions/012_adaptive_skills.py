"""Tenant-local skills, decision/outcome evidence and trained selector bundles."""
from pathlib import Path
from alembic import op

revision='012_adaptive_skills'
down_revision='011_verified_learning'
branch_labels=None
depends_on=None

TABLES=['adaptive_skills','adaptive_skill_revisions','adaptive_cases','adaptive_work','adaptive_models',
    'adaptive_contexts','adaptive_decisions','adaptive_outcomes','adaptive_label_revisions','adaptive_controls']


def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).parents[1]/'adaptive_schema_v1.sql').read_text())
    for name in TABLES:
        op.execute(f'ALTER TABLE {name} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {name} FORCE ROW LEVEL SECURITY')
        predicate=f"""workspace_id::text=current_setting('app.workspace_id',true) AND EXISTS (
          SELECT 1 FROM workspaces w JOIN tenants t ON t.id=w.tenant_id AND t.tenant_status='active'
          JOIN tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
          JOIN users u ON u.id=tm.user_id AND u.is_active
          LEFT JOIN workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
          WHERE w.id={name}.workspace_id AND w.status='active' AND u.id::text=current_setting('app.actor_id',true)
          AND tm.role IN ('viewer','analyst','admin','owner')
          AND (tm.role IN ('admin','owner') OR wm.role IN ('viewer','analyst','admin','owner')))"""
        op.execute(f'CREATE POLICY adaptive_scope ON {name} USING ({predicate}) WITH CHECK ({predicate})')
    for name in ['adaptive_skill_revisions','adaptive_decisions','adaptive_label_revisions','adaptive_contexts']:
        op.execute(f'CREATE TRIGGER immutable_evidence BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION learning_immutable_v1()')
    op.execute("""CREATE FUNCTION adaptive_content_immutable_v1() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable adaptive content'; END IF;
        IF (to_jsonb(OLD)-ARRAY['state','test_result','activated_at','available','invalid_reason']) IS DISTINCT FROM
           (to_jsonb(NEW)-ARRAY['state','test_result','activated_at','available','invalid_reason'])
        THEN RAISE EXCEPTION 'Immutable adaptive content'; END IF;
        RETURN NEW;
      END; $$""")
    for name in ['adaptive_skills','adaptive_cases','adaptive_models']:
        op.execute(f'CREATE TRIGGER immutable_content BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION adaptive_content_immutable_v1()')
    op.execute("""CREATE FUNCTION adaptive_outcome_immutable_v1() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Immutable action evidence'; END IF;
        IF (to_jsonb(OLD)-ARRAY['label_status','revision']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['label_status','revision'])
        THEN RAISE EXCEPTION 'Immutable action evidence'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute('CREATE TRIGGER immutable_action BEFORE UPDATE OR DELETE ON adaptive_outcomes FOR EACH ROW EXECUTE FUNCTION adaptive_outcome_immutable_v1()')


def downgrade():
    # Respect FK dependency order, preserving all pre-upgrade learning tables.
    for name in ['adaptive_label_revisions','adaptive_outcomes','adaptive_decisions','adaptive_contexts',
                 'adaptive_controls','adaptive_models','adaptive_work','adaptive_cases','adaptive_skill_revisions','adaptive_skills']:
        op.drop_table(name)
    op.execute('DROP FUNCTION adaptive_content_immutable_v1()')
    op.execute('DROP FUNCTION IF EXISTS adaptive_outcome_immutable_v1()')
