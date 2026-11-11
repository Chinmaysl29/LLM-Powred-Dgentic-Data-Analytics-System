"""Synthetic browser pilot through real authenticated APIs and live durable worker."""
from copy import deepcopy
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx
from sqlalchemy.engine import make_url

from seed_learning_browser import main as seed_identity


def main():
    if make_url(os.environ['DATABASE_URL']).database!='analyst_setup_test' or os.environ.get('ENVIRONMENT')!='test':
        raise SystemExit('Dedicated synthetic test environment only')
    seed_identity()
    account=json.loads(Path('/verification/learning-browser-account.json').read_text())
    workspace=account['workspace_id']
    with httpx.Client(base_url='http://api:8000',timeout=90) as client:
        def request(method,path,body=None,expected=200,**kwargs):
            response=client.request(method,path,json=body,**kwargs)
            assert response.status_code==expected,(path,response.status_code,response.text[:1000])
            return response.json()
        login=request('POST','/api/v1/auth/login',{'email':account['email'],'password':account['password']})
        client.headers['Authorization']='Bearer '+login['access_token']
        def path(part):return f'/api/v1/adaptive/{part}?workspace_id={workspace}'
        request('POST',path('skills/bootstrap'),expected=201)
        request('PUT',path('controls'),{'mode':'collection','expected_generation':0})
        request('POST',f'/api/v1/learning/definitions?workspace_id={workspace}',{
            'key':'net_revenue','version':1,'owner':'Synthetic finance owner','source':'Independent 300 minus 15 fixture',
            'metric':{'column':'net_amount','aggregation':'sum','missing':'reject','definition_ref':None},
            'filters':[],'units':'USD','currency':'USD','examples':[{'orders_total':300,'refund_total':15,'net':285}]},201)
        fixtures=json.loads(Path('/verification/adaptive-evidence/synthetic-fixtures.json').read_text())
        splits={name:[] for name in ['train','development','final']}
        for index,fixture in enumerate(fixtures):
            upload=request('POST',f'/api/v1/datasets/upload?workspace_id={workspace}',expected=201,
                files={'file':(f'synthetic_selector_{index}.csv',fixture['csv'].encode(),'text/csv')})
            dataset=upload['dataset_id']
            request('POST',f'/api/v1/datasets/{dataset}/workspace',{'workspace_id':workspace})
            body=deepcopy(fixture['contract_and_gold']);body['task']['workspace_id']=workspace
            body['task']['datasets'][0]['dataset_id']=dataset
            case=request('POST',path('cases'),body,201)
            splits[body['split']].append(case['id'])
        def wait(identifier):
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                job=request('GET',path(f'jobs/{identifier}'))
                if job['state'] in {'succeeded','insufficient_evidence','failed'}:
                    assert job['state']=='succeeded',job
                    return job
                time.sleep(.5)
            raise AssertionError('Durable synthetic job timed out')
        replay=request('POST',path('replays'),{'case_ids':splits['train']+splits['development'],'idempotency_key':uuid4().hex},202)
        wait(replay['id'])
        training=request('POST',path('training'),{'train_case_ids':splits['train'],'development_case_ids':splits['development'],
            'final_case_ids':splits['final'],'max_epochs':60,'idempotency_key':uuid4().hex},202)
        trained=wait(training['id'])
        assert trained['result']['trained'] and not trained['result']['release_eligible']
        account['linear_model_id']=trained['result']['models']['linear'];account['training_job_id']=training['id']
        Path('/verification/adaptive-browser-account.json').write_text(json.dumps(account))
        print('Synthetic identity, reviewed definition, 40 cases and two real trained candidates ready. Secrets kept in test volume.')


if __name__=='__main__':main()
