"""Coordinate a real isolated worker kill via a marker; never touches live storage."""
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4
import httpx

assert os.environ.get('ENVIRONMENT') == 'test'
root=Path('/verification')
account=json.loads((root/'learning-browser-account.json').read_text())
fixture=root/'audit-worker-input.csv'
with fixture.open('wb') as stream:
    stream.write(b'region,amount,label\n')
    block=b'east,10,synthetic\n'*10000
    for _ in range(400):
        stream.write(block)
digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
with httpx.Client(base_url='http://api:8000',timeout=120) as client:
    for _ in range(120):
        try:
            if client.get('/health/ready').status_code==200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise AssertionError('Isolated API startup deadline')
    login=client.post('/api/v1/auth/login',json={'email':account['email'],'password':account['password']})
    assert login.status_code==200
    client.headers['Authorization']='Bearer '+login.json()['access_token']
    scope={'workspace_id':account['workspace_id']}
    with fixture.open('rb') as stream:
        response=client.post('/api/v1/dataplane/upload',data={**scope,'idempotency_key':uuid4().hex},files={'file':('audit-worker.csv',stream,'text/csv')})
    assert response.status_code==202,response.status_code
    job=response.json();observed=False;started=time.monotonic()
    while time.monotonic()-started<180:
        state=client.get('/api/v1/dataplane/jobs/'+job['id'],params=scope).json()
        if state['status']=='RUNNING' and not observed:
            (root/'audit-worker-kill-ready-2').write_text(job['id'])
            observed=True
        if state['status'] in ('READY','FAILED','CANCELLED'):
            record={'status':state['status'],'attempt':state['attempt'],'running_observed':observed,'elapsed_s':time.monotonic()-started}
            if state['status']=='READY':
                snapshot=client.get('/api/v1/dataplane/artifacts/'+state['result']['artifact_id'],params=scope).json()
                record.update(rows=snapshot['payload']['row_count'],source_hash_matches=snapshot['payload']['original']['sha256']==digest)
            (root/'audit-worker-result.json').write_text(json.dumps(record,indent=2))
            print(json.dumps(record))
            break
        time.sleep(.1)
    else:
        raise AssertionError('Worker recovery exceeded 180 seconds')
