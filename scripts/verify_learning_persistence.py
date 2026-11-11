"""Compare the exact supervised export after isolated PostgreSQL/API restart."""
import hashlib
import json
import os
from pathlib import Path
import time

import httpx
from sqlalchemy.engine import make_url


def main():
    if make_url(os.environ['DATABASE_URL']).database != 'analyst_setup_test' or os.environ.get('ENVIRONMENT') != 'test':
        raise SystemExit('Dedicated synthetic test environment only')
    account=json.loads(Path('/verification/learning-browser-account.json').read_text())
    report_path=Path('/verification/learning-evidence/browser/verified-report.json')
    saved=report_path.read_bytes();run_id=json.loads(saved)['run_id']
    with httpx.Client(base_url='http://api:8000',timeout=30) as client:
        for _ in range(60):
            try:
                if client.get('/health/ready').status_code==200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise SystemExit('Synthetic API did not become ready')
        login=client.post('/api/v1/auth/login',json={'email':account['email'],'password':account['password']})
        assert login.status_code==200
        client.headers['Authorization']='Bearer '+login.json()['access_token']
        status=client.get(f'/api/v1/learning/runs/{run_id}')
        assert status.status_code==200 and status.json()['state']=='succeeded'
        response=client.get(f'/api/v1/learning/runs/{run_id}/report')
        assert response.status_code==200 and response.content==saved,'Supervised report bytes changed after restart'
        result={'run_restored':True,'exact_report_bytes_restored':True,'bytes':len(saved),
            'sha256':hashlib.sha256(saved).hexdigest(),'scope':'Synthetic local/test PostgreSQL and API restart; real auth and export'}
        Path('/verification/learning-evidence/persistence.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
