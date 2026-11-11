"""Actual authenticated report authorization and export regressions."""
from sqlalchemy import update
from backend.tests.test_analysis_history_and_reports import (
    settings, db_engine, db_session, client, make_test_user_and_workspace,
)
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships


def report_source(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr('backend.app.api.v1.routes.analysis_history.REPORT_STUDIO_STORAGE_ROOT', tmp_path/'reports')
    owner, token, workspace=make_test_user_and_workspace(db_session,'repair_report_owner')
    headers={'Authorization':'Bearer '+token}
    uploaded=client.post('/api/v1/datasets/upload',params={'workspace_id':str(workspace.id)},
        headers=headers,files={'file':('audit.csv',b'region,amount\neast,10\nwest,25\n','text/csv')})
    assert uploaded.status_code==201
    dataset=uploaded.json()['dataset_id']
    bound=client.post(f'/api/v1/datasets/{dataset}/workspace',headers=headers,json={'workspace_id':str(workspace.id)})
    assert bound.status_code==200
    response=client.post('/api/v1/chat',headers=headers,json={
        'message':'What is the total amount?','dataset_id':dataset,'workspace_id':str(workspace.id)})
    assert response.status_code==200 and response.json()['status']=='complete'
    return owner,workspace,headers,response.json()


def test_f012_report_guessing_and_revoked_workspace_are_denied(client,db_session,monkeypatch,tmp_path):
    owner,workspace,headers,analysis=report_source(client,db_session,monkeypatch,tmp_path)
    generated=client.post('/api/v1/reports/from-analysis',headers=headers,json={
        'run_id':analysis['run_id'],'session_id':analysis['session_id'],'title':'Private synthetic report','format_type':'pdf'})
    assert generated.status_code==201
    report_id=generated.json()['id']
    _,other_token,_=make_test_user_and_workspace(db_session,'repair_report_other')
    for suffix in ('','/download'):
        path=f'/api/v1/reports/{report_id}{suffix}'
        allowed=client.get(path,headers=headers)
        assert allowed.status_code==200
        denied=client.get(path,headers={'Authorization':'Bearer '+other_token})
        assert denied.status_code==404
    db_session.execute(update(workspace_memberships).where(
        workspace_memberships.c.workspace_id==workspace.id,
        workspace_memberships.c.user_id==owner.id).values(active=False))
    # Tenant owners retain workspace authority until tenant membership is revoked.
    db_session.execute(update(tenant_memberships).where(
        tenant_memberships.c.tenant_id==workspace.tenant_id,
        tenant_memberships.c.user_id==owner.id).values(active=False))
    db_session.commit()
    for suffix in ('','/download'):
        revoked=client.get(f'/api/v1/reports/{report_id}{suffix}',headers=headers)
        assert revoked.status_code==404
