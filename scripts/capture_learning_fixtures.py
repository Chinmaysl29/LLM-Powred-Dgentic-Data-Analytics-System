"""Export only the known synthetic pilot, checking its saved result hashes.

The test driver regenerates these same literal scenarios on every verification
run. This artifact makes the input bytes, gold rubric, definition and frozen
memory available alongside the UUID-based evaluation manifest.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    if make_url(os.environ['DATABASE_URL']).database != 'analyst_setup_test' or os.environ.get('ENVIRONMENT') != 'test':
        raise SystemExit('Dedicated synthetic test database only')
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, 'env_file': None}; get_settings.cache_clear()
    from backend.app.models.learning import LearningBundle, LearningCase, LearningLesson, LearningRun
    from backend.app.schemas.learning import TaskSpec
    from backend.app.services.learning_engine import digest, execute, frame_hash, load_preserved_frame
    from backend.app.services.learning_supervisor import definitions
    output=Path('/verification/learning-evidence')
    manifest=json.loads((output/'synthetic-manifest.json').read_text())
    results=json.loads((output/'synthetic-results.json').read_text())
    literal_cases={
        'new-business-scenario':'region,amount,status\nb,200,paid\nb,-10,refund\nb,900,cancelled\n',
        'another-scenario':'region,amount,status\nc,40,paid\nc,-5,refund\n',
    }
    source_csv='region,amount,status\na,100,paid\na,1000,cancelled\na,-20,refund\na,100,paid\n'
    engine=create_engine(get_settings().postgres_dsn)
    with Session(engine) as db, tempfile.TemporaryDirectory(prefix='synthetic-fixture-capture-') as scratch:
        bundle=db.get(LearningBundle,manifest['candidate_bundle'])
        assert bundle and bundle.content_hash==digest(bundle.content)
        exported=[]
        for case_id in manifest['case_ids']:
            case=db.get(LearningCase,case_id)
            assert case and case.content['label_source']=='synthetic' and case.scenario_group in literal_cases
            task=TaskSpec.model_validate(case.content['task'])
            csv=literal_cases[case.scenario_group]
            path=Path(scratch)/'case.csv';path.write_text(csv)
            frame=load_preserved_frame(path,'csv')
            outcome=execute(task,frame,definitions(db,task.workspace_id))
            saved=next(pair for pair in results['pairs'] if pair['case_id']==case_id)
            assert outcome['result_hash']==saved['baseline']['result_hash'],'Synthetic input does not reproduce stored result'
            exported.append({'case_id':case_id,'contract_and_gold':case.content,'csv':csv,'source_hash':frame_hash(frame)})
        lessons=[]
        source=None
        for ref in bundle.content['lessons']:
            lesson=db.get(LearningLesson,ref['id'])
            assert lesson and lesson.content_hash==ref['content_hash']
            lessons.append({'frozen_reference':ref,'immutable_content':lesson.content})
            source=db.get(LearningRun,lesson.source_run_id)
            assert source and source.task['objective']=='Net revenue by region'
            path=Path(scratch)/'source.csv';path.write_text(source_csv)
            assert frame_hash(load_preserved_frame(path,'csv'))==source.outcome['profile']['source_hash']
        assert source
        result={'kind':'synthetic pilot only','source':{'task':source.task,'csv':source_csv},
            'business_definitions':definitions(db,source.workspace_id),'cases':exported,'frozen_bundle':bundle.content,
            'frozen_lessons':lessons,'verification':'Regenerated CSV inputs reproduce both saved baseline result hashes; source fingerprint matches.'}
        (output/'synthetic-fixtures.json').write_text(json.dumps(result,indent=2))
    engine.dispose()
    print('Known synthetic source/held-out fixtures captured; saved baseline result hashes independently reproduced.')


if __name__=='__main__':
    main()
