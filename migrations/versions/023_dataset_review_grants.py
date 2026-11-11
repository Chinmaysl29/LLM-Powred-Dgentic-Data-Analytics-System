"""Explicit dataset reviewer grants; no raw-source or execution access."""
from alembic import op
import sqlalchemy as sa

revision = '023_dataset_review_grants'
down_revision = '022_active_version_guard'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dataset_review_grants',
        sa.Column('id', sa.Uuid, primary_key=True),
        sa.Column('tenant_id', sa.Uuid, sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('workspace_id', sa.Uuid, sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.dataset_id'), nullable=False),
        sa.Column('owner_id', sa.Uuid, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reviewer_id', sa.Uuid, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('active', sa.Boolean, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('dataset_id', 'owner_id', 'reviewer_id', name='uq_dataset_reviewer_owner'),
        sa.CheckConstraint('owner_id <> reviewer_id', name='ck_review_grant_no_self'),
        sa.CheckConstraint('revision >= 1', name='ck_review_grant_revision'))
    op.create_index('ix_review_grant_reviewer_scope', 'dataset_review_grants', ['reviewer_id', 'workspace_id', 'active'])
    op.create_index('ix_review_grant_owner_scope', 'dataset_review_grants', ['owner_id', 'workspace_id'])
    schema = op.get_bind().scalar(sa.text('SELECT current_schema()'))
    quoted = op.get_bind().dialect.identifier_preparer.quote(schema)
    scope = f"""tenant_id::text=current_setting('app.tenant_id',true)
      AND workspace_id::text=current_setting('app.workspace_id',true)
      AND EXISTS (SELECT 1 FROM {quoted}.workspaces w JOIN {quoted}.tenants t ON t.id=w.tenant_id
        JOIN {quoted}.tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
        JOIN {quoted}.users u ON u.id=tm.user_id AND u.is_active
        LEFT JOIN {quoted}.workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
        WHERE w.id=workspace_id AND w.tenant_id=tenant_id AND w.status='active' AND t.tenant_status='active'
          AND u.id::text=current_setting('app.actor_id',true)
          AND tm.role IN ('viewer','analyst','admin','owner')
          AND (tm.role IN ('owner','admin') OR wm.role IN ('viewer','analyst','admin','owner')))"""
    # Qualify these correlated identifiers: joined membership tables also have workspace_id.
    scope = scope.replace('w.id=workspace_id', 'w.id=dataset_review_grants.workspace_id').replace(
        'w.tenant_id=tenant_id', 'w.tenant_id=dataset_review_grants.tenant_id')
    owner = f"""EXISTS (SELECT 1 FROM {quoted}.datasets d JOIN {quoted}.dataset_workspace_bindings b ON b.dataset_id=d.dataset_id
      WHERE d.dataset_id=dataset_review_grants.dataset_id AND b.workspace_id=dataset_review_grants.workspace_id
        AND d.owner_id=current_setting('app.actor_id',true))"""
    manager = f"""EXISTS (SELECT 1 FROM {quoted}.tenant_memberships tm
      LEFT JOIN {quoted}.workspace_memberships wm ON wm.workspace_id=dataset_review_grants.workspace_id
        AND wm.user_id=tm.user_id AND wm.active
      WHERE tm.tenant_id=dataset_review_grants.tenant_id AND tm.user_id::text=current_setting('app.actor_id',true)
        AND tm.active AND (tm.role IN ('owner','admin') OR wm.role IN ('owner','admin')))"""
    op.execute('ALTER TABLE dataset_review_grants ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE dataset_review_grants FORCE ROW LEVEL SECURITY')
    op.execute(f"CREATE POLICY review_grant_read ON dataset_review_grants FOR SELECT USING ({scope} AND ({owner} OR {manager} OR reviewer_id::text=current_setting('app.actor_id',true)))")
    op.execute(f"CREATE POLICY review_grant_insert ON dataset_review_grants FOR INSERT WITH CHECK ({scope} AND {owner} AND owner_id::text=current_setting('app.actor_id',true))")
    op.execute(f"CREATE POLICY review_grant_update ON dataset_review_grants FOR UPDATE USING ({scope} AND ({owner} OR {manager})) WITH CHECK ({scope} AND (({owner} AND owner_id::text=current_setting('app.actor_id',true)) OR (NOT active AND ({owner} OR {manager}))))")
    op.execute(f"""CREATE FUNCTION {quoted}.review_grant_identity_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF ROW(OLD.id,OLD.tenant_id,OLD.workspace_id,OLD.dataset_id,OLD.owner_id,OLD.reviewer_id,OLD.created_at)
          IS DISTINCT FROM ROW(NEW.id,NEW.tenant_id,NEW.workspace_id,NEW.dataset_id,NEW.owner_id,NEW.reviewer_id,NEW.created_at)
        THEN RAISE EXCEPTION 'Immutable review grant identity'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute(f'CREATE TRIGGER review_grant_identity BEFORE UPDATE ON dataset_review_grants FOR EACH ROW EXECUTE FUNCTION {quoted}.review_grant_identity_guard()')

    # This narrow function is the sole delegated read path. Existing artifact RLS
    # remains owner-only; no caller receives raw payloads, parameters or file paths.
    op.execute(f"""CREATE FUNCTION {quoted}.company_review_artifact(p_id uuid, p_dataset text DEFAULT NULL)
      RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE item record; safe jsonb; masked jsonb;
      BEGIN
        SELECT a.* INTO item FROM {quoted}.dataplane_artifacts a
          JOIN {quoted}.datasets d ON d.dataset_id=a.dataset_id AND d.owner_id=a.actor_id::text
          JOIN {quoted}.users source_owner ON source_owner.id=a.actor_id AND source_owner.is_active
          JOIN {quoted}.dataset_workspace_bindings b ON b.dataset_id=d.dataset_id AND b.workspace_id=a.workspace_id
          JOIN {quoted}.dataset_review_grants g ON g.dataset_id=d.dataset_id AND g.workspace_id=a.workspace_id
            AND g.tenant_id=a.tenant_id AND g.owner_id=a.actor_id AND g.active AND g.expires_at>clock_timestamp()
          JOIN {quoted}.workspaces w ON w.id=a.workspace_id AND w.tenant_id=a.tenant_id AND w.status='active'
          JOIN {quoted}.tenants t ON t.id=w.tenant_id AND t.tenant_status='active'
          JOIN {quoted}.users u ON u.id=g.reviewer_id AND u.is_active
          JOIN {quoted}.tenant_memberships tm ON tm.tenant_id=t.id AND tm.user_id=u.id AND tm.active
          LEFT JOIN {quoted}.workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
        WHERE a.tenant_id::text=current_setting('app.tenant_id',true)
          AND a.workspace_id::text=current_setting('app.workspace_id',true)
          AND u.id::text=current_setting('app.actor_id',true)
          AND tm.role IN ('viewer','analyst','admin','owner')
          AND (tm.role IN ('admin','owner') OR wm.role IN ('viewer','analyst','admin','owner'))
          AND d.status NOT IN ('deleted','archived','purged')
          AND (p_dataset IS NULL OR a.dataset_id=p_dataset)
          AND ((p_id IS NULL AND p_dataset IS NOT NULL AND a.kind='snapshot') OR a.id=p_id)
          AND (a.kind='snapshot' OR (a.kind IN ('evidence','workflow')
            AND (a.kind='workflow' OR a.payload->>'contract_version'='1')
            AND EXISTS (SELECT 1 FROM {quoted}.dataplane_artifacts r
              WHERE r.parent_id=a.id AND r.kind='review' AND r.payload->>'status'='review')))
        ORDER BY a.created_at DESC,a.id DESC LIMIT 1;
        IF NOT FOUND THEN RETURN NULL; END IF;
        safe := item.payload - ARRAY['sql','parameters','estimate','curated','files','original','quarantine','encrypted','report_artifact','preview_rows'];
        IF item.kind='evidence' THEN
          SELECT coalesce(jsonb_agg(x || jsonb_build_object('value','[redacted]')), '[]'::jsonb) INTO masked
            FROM jsonb_array_elements(coalesce(safe#>'{{plan,filters}}','[]'::jsonb)) x;
          safe := jsonb_set(safe,'{{plan,filters}}',masked,true);
        ELSIF item.kind='workflow' THEN
          SELECT coalesce(jsonb_agg(x || jsonb_build_object('value','[redacted]')), '[]'::jsonb) INTO masked
            FROM jsonb_array_elements(coalesce(safe#>'{{spec,query,plan,filters}}','[]'::jsonb)) x;
          safe := jsonb_set(safe,'{{spec,query,plan,filters}}',masked,true);
        END IF;
        RETURN jsonb_build_object('id',item.id,'kind',item.kind,'dataset_id',item.dataset_id,
          'actor_id',item.actor_id,'workspace_id',item.workspace_id,'tenant_id',item.tenant_id,
          'parent_id',item.parent_id,'payload',safe,'created_at',item.created_at);
      END; $$""")
    op.execute(f'REVOKE ALL ON FUNCTION {quoted}.company_review_artifact(uuid,text) FROM PUBLIC')
    op.execute(f"""CREATE FUNCTION {quoted}.company_review_queue(p_offset integer DEFAULT 0)
      RETURNS SETOF jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE candidate record; permitted jsonb;
      BEGIN
        IF p_offset<0 OR p_offset>100000 THEN RAISE EXCEPTION 'Invalid review page'; END IF;
        FOR candidate IN
          SELECT a.id FROM {quoted}.dataplane_artifacts a
            JOIN {quoted}.dataset_review_grants g ON g.dataset_id=a.dataset_id AND g.owner_id=a.actor_id
              AND g.workspace_id=a.workspace_id AND g.tenant_id=a.tenant_id AND g.active AND g.expires_at>clock_timestamp()
          WHERE a.kind IN ('evidence','workflow')
            AND a.workspace_id::text=current_setting('app.workspace_id',true)
            AND a.tenant_id::text=current_setting('app.tenant_id',true)
            AND g.reviewer_id::text=current_setting('app.actor_id',true)
            AND (SELECT r.payload->>'status' FROM {quoted}.dataplane_artifacts r
              WHERE r.parent_id=a.id AND r.kind='review'
              ORDER BY (r.payload->>'revision')::integer DESC LIMIT 1)='review'
          ORDER BY a.created_at DESC,a.id DESC LIMIT 51 OFFSET p_offset
        LOOP
          permitted := {quoted}.company_review_artifact(candidate.id,NULL);
          IF permitted IS NOT NULL THEN RETURN NEXT permitted; END IF;
        END LOOP;
      END; $$""")
    op.execute(f'REVOKE ALL ON FUNCTION {quoted}.company_review_queue(integer) FROM PUBLIC')
    op.execute('REVOKE ALL ON dataset_review_grants FROM PUBLIC')
    # Shared review events contain lifecycle evidence only. Owners retain historical
    # approvals after a grant expires; revoked reviewers lose new read/write access.
    review_scope = f"""tenant_id::text=current_setting('app.tenant_id',true)
      AND workspace_id::text=current_setting('app.workspace_id',true) AND kind='review'
      AND EXISTS (SELECT 1 FROM {quoted}.workspaces w JOIN {quoted}.tenants t ON t.id=w.tenant_id
        JOIN {quoted}.tenant_memberships tm ON tm.tenant_id=t.id AND tm.active
        JOIN {quoted}.users u ON u.id=tm.user_id AND u.is_active
        LEFT JOIN {quoted}.workspace_memberships wm ON wm.workspace_id=w.id AND wm.user_id=u.id AND wm.active
        WHERE w.id=dataplane_artifacts.workspace_id AND w.tenant_id=dataplane_artifacts.tenant_id
          AND w.status='active' AND t.tenant_status='active' AND u.id::text=current_setting('app.actor_id',true)
          AND tm.role IN ('viewer','analyst','admin','owner')
          AND (tm.role IN ('owner','admin') OR wm.role IN ('viewer','analyst','admin','owner')))"""
    owner_review = f"""EXISTS (SELECT 1 FROM {quoted}.datasets d JOIN {quoted}.dataset_workspace_bindings b ON b.dataset_id=d.dataset_id
      WHERE d.dataset_id=dataplane_artifacts.dataset_id AND b.workspace_id=dataplane_artifacts.workspace_id
        AND d.owner_id=current_setting('app.actor_id',true) AND d.status NOT IN ('deleted','archived','purged'))"""
    op.execute(f"CREATE POLICY company_review_history ON dataplane_artifacts FOR SELECT USING ({review_scope} AND ({owner_review} OR {quoted}.company_review_artifact(parent_id,dataset_id) IS NOT NULL))")
    op.execute(f"CREATE POLICY company_peer_approval ON dataplane_artifacts FOR INSERT WITH CHECK ({review_scope} AND actor_id::text=current_setting('app.actor_id',true) AND payload->>'status'='approved' AND {quoted}.company_review_artifact(parent_id,dataset_id) IS NOT NULL)")
    op.create_index('uq_company_review_revision', 'dataplane_artifacts', ['parent_id', sa.text("((payload->>'revision')::integer)")],
                    unique=True, postgresql_where=sa.text("kind='review'"))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM dataset_review_grants)')):
        raise RuntimeError('Archive dataset reviewer grants before downgrade')
    schema = op.get_bind().scalar(sa.text('SELECT current_schema()'))
    quoted = op.get_bind().dialect.identifier_preparer.quote(schema)
    op.execute('DROP POLICY company_peer_approval ON dataplane_artifacts')
    op.execute('DROP POLICY company_review_history ON dataplane_artifacts')
    op.drop_index('uq_company_review_revision', table_name='dataplane_artifacts')
    op.execute(f'DROP FUNCTION {quoted}.company_review_queue(integer)')
    op.execute(f'DROP FUNCTION {quoted}.company_review_artifact(uuid,text)')
    op.drop_table('dataset_review_grants')
    op.execute(f'DROP FUNCTION {quoted}.review_grant_identity_guard()')
