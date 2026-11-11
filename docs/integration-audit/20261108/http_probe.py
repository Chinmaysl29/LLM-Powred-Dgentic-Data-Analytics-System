"""Read/append-only synthetic audit probes. Run only in the isolated test project."""
import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4
import httpx

assert os.environ.get('ENVIRONMENT') == 'test'
parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['auth', 'auth-restart', 'dataplane', 'chat'], required=True)
parser.add_argument('--skip-ready', action='store_true')
args = parser.parse_args()
base = Path('/verification')
with httpx.Client(base_url='http://api:8000', timeout=90) as client:
    for _ in range(0 if args.skip_ready else 90):
        try:
            if client.get('/health/ready').status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    if args.mode == 'auth':
        email, password = 'audit-'+uuid4().hex+'@example.com', 'Audit-'+uuid4().hex+'-9!'
        assert client.post('/api/v1/auth/register', json={'email':email,'password':password,'full_name':'Synthetic audit'}).status_code == 201
        login = client.post('/api/v1/auth/login', json={'email':email,'password':password})
        assert login.status_code == 200
        tokens = login.json()
        client.headers['Authorization'] = 'Bearer '+tokens['access_token']
        before = client.get('/api/v1/auth/me').status_code
        logout = client.post('/api/v1/auth/logout', json={'refresh_token':tokens['refresh_token']}).status_code
        after = client.get('/api/v1/auth/me').status_code
        refresh = client.post('/api/v1/auth/refresh', json={'refresh_token':tokens['refresh_token']}).status_code
        (base/'audit-private-auth.json').write_text(json.dumps(tokens))
        print(json.dumps({'mode':'auth','before_logout':before,'logout':logout,'after_logout':after,'revoked_refresh':refresh}))
    elif args.mode == 'auth-restart':
        tokens = json.loads((base/'audit-private-auth.json').read_text())
        client.headers['Authorization'] = 'Bearer '+tokens['access_token']
        print(json.dumps({'mode':'auth-restart','revoked_access':client.get('/api/v1/auth/me').status_code,'revoked_refresh':client.post('/api/v1/auth/refresh',json={'refresh_token':tokens['refresh_token']}).status_code}))
    else:
        account = json.loads((base/'learning-browser-account.json').read_text())
        login = client.post('/api/v1/auth/login', json={'email':account['email'],'password':account['password']})
        assert login.status_code == 200
        client.headers['Authorization'] = 'Bearer '+login.json()['access_token']
        scope = {'workspace_id':account['workspace_id']}
        if args.mode == 'chat':
            started=time.perf_counter()
            r=client.post('/api/v1/chat',json={'message':'What is the total amount?','dataset_id':account['dataset_id'],**scope})
            body=r.json()
            print(json.dumps({'mode':'chat','http':r.status_code,'status':body.get('status'),'answer':body.get('answer'),'data':body.get('data'),'has_run':bool(body.get('run_id')),'elapsed_s':time.perf_counter()-started}))
        else:
            def finish(job):
                for _ in range(90):
                    response=client.get('/api/v1/dataplane/jobs/'+job['id'],params=scope)
                    assert response.status_code==200
                    state=response.json()
                    if state['status'] in ('READY','FAILED','CANCELLED'):
                        assert state['status']=='READY',state
                        return client.get('/api/v1/dataplane/artifacts/'+state['result']['artifact_id'],params=scope).json()
                    time.sleep(1)
                raise AssertionError('Job deadline')
            upload=client.post('/api/v1/dataplane/upload',data={**scope,'idempotency_key':uuid4().hex},files={'file':('audit.csv',b'region,amount\neast,10\neast,5\nwest,20\n','text/csv')})
            assert upload.status_code==202
            snapshot=finish(upload.json())
            metric=client.post('/api/v1/dataplane/metrics',params=scope,json={'dataset_id':snapshot['dataset_id'],'snapshot_id':snapshot['id'],'definition':{'name':'audit_amount','column':'amount','aggregation':'sum','description':'Sum source amount'}})
            assert metric.status_code==201
            message={'message':'What is the total amount?','dataset_id':snapshot['dataset_id'],**scope}
            first=client.post('/api/v1/chat',json=message)
            record={'mode':'dataplane-chat','first_http':first.status_code,'first_status':first.json().get('status')}
            if first.status_code==200 and first.json().get('status')=='queued':
                evidence=finish({'id':first.json()['plan']['job_id']})
                second=client.post('/api/v1/chat',json=message)
                record.update(second_http=second.status_code,second_status=second.json().get('status'),data=second.json().get('data'),citations=second.json().get('citations'),chart=second.json().get('chart'),kpis=second.json().get('kpis'),evidence_rows=evidence['payload']['rows'])
                for fmt in ('pdf','xlsx','csv'):
                    report=client.post('/api/v1/reports/from-analysis',json={'run_id':second.json()['run_id'],'session_id':second.json()['session_id'],'title':'Synthetic audit','format_type':fmt,'report_type':'Executive Report'})
                    item={'create':report.status_code}
                    if report.status_code==201:
                        download=client.get('/api/v1/reports/'+report.json()['id']+'/download')
                        item.update(download=download.status_code,bytes=len(download.content))
                        (base/('audit-export.'+fmt)).write_bytes(download.content)
                    record[fmt]=item
            print(json.dumps(record))
