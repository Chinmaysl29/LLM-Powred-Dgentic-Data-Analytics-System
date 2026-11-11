"""Verify byte-identical private report/model downloads after test service restart."""
import hashlib
import json
import os
from pathlib import Path
import time

import httpx
from sqlalchemy.engine import make_url


def main():
    if make_url(os.environ['DATABASE_URL']).database!='analyst_setup_test' or os.environ.get('ENVIRONMENT')!='test':
        raise SystemExit('Dedicated synthetic test environment only')
    account=json.loads(Path('/verification/adaptive-browser-account.json').read_text())
    output=Path('/verification/adaptive-evidence');browser=output/'browser'
    files=[('net-revenue-report.json','report'),('refund-events-report.json','report'),('linear-model-bundle.json','model')]
    checked=[]
    with httpx.Client(base_url='http://api:8000',timeout=30) as client:
        for _ in range(60):
            try:
                if client.get('/health/ready').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(1)
        else:raise SystemExit('Synthetic API did not become ready')
        login=client.post('/api/v1/auth/login',json={'email':account['email'],'password':account['password']})
        assert login.status_code==200
        client.headers['Authorization']='Bearer '+login.json()['access_token']
        for filename,kind in files:
            saved=(browser/filename).read_bytes();payload=json.loads(saved)
            path=(f'/api/v1/learning/runs/{payload["run_id"]}/report' if kind=='report' else
                  f'/api/v1/adaptive/models/{payload["id"]}/download?workspace_id={account["workspace_id"]}')
            response=client.get(path)
            assert response.status_code==200 and response.content==saved,f'{kind} bytes changed after restart'
            checked.append({'artifact':filename,'bytes':len(saved),'sha256':hashlib.sha256(saved).hexdigest(),'byte_identical':True})
        controls=client.get(f'/api/v1/adaptive/controls?workspace_id={account["workspace_id"]}').json()
        assert controls['mode']=='collection' and controls['effective_selector']=='rules-memory-v1'
    result={'postgresql_api_restart':True,'artifacts':checked,'rollback_persisted':True,'scope':'Real local/test auth, PostgreSQL and API; synthetic data only'}
    (output/'persistence.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':main()
