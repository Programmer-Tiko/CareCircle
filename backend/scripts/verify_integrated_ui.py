"""Real Chrome/microphone + localhost HTTP + isolated PostgreSQL UI acceptance.

Run from repository root. Requires TEST_CONVERSATION_DB_URL, installed Chrome,
and Playwright supplied via CADENCE_PLAYWRIGHT_MODULE. Provider calls are stubbed
explicitly in browser requests; corpus selection uses deterministic eligible IDs.
No cloud credentials, existing profiles or schemas are modified.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
sys.path.insert(0, str(ROOT/'backend/scripts'))
from app.api import main as api
from app.api.conversations import get_selector
from app.dialogue.conversation_adapter import selector_adapter
from verify_live_workflow import serve


def run(output):
    url = os.environ['TEST_CONVERSATION_DB_URL']
    schema = 'cadence_integrated_ui_' + uuid4().hex
    with psycopg.connect(url) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(url, row_factory=dict_row, options=f'-csearch_path={schema},public')
    calls=[]
    try:
        with connect() as db:
            ddl = (ROOT/'backend/app/api/schema.sql').read_text()
            ddl = '\n'.join(line for line in ddl.splitlines() if not line.startswith(
                ('CREATE EXTENSION','SELECT create_hypertable')))
            db.execute(ddl)
            db.execute(ddl)  # additive schema updates must be idempotent
        app = api.create_app()
        def database():
            with connect() as db:
                yield db
        def selector(context):
            # Exercise the actual retrieval, adapter, source validation and
            # rendered corpus templates. Only the provider ID choice is stubbed.
            if len(context['turns']) >= 3:
                return {'decision':'complete','resolved':True}
            def choose(prompt):
                payload=json.loads(prompt)
                unit=payload['eligible_questions'][0]
                return json.dumps({'selected_question_id':unit['id'],'evidence_ids':[unit['id']],
                    'patient_quote':payload['patient_answer'],'abstain':False})
            result=selector_adapter(context,model_call=choose)
            calls.append({'turn_count':len(context['turns']),'decision':result['decision'],
                          'question_id':(result.get('question') or {}).get('id')})
            return result
        app.dependency_overrides[api.get_db]=database
        app.dependency_overrides[get_selector]=lambda:selector
        source, rate = sf.read(ROOT/'backend/tests/fixtures/speech_chunk.wav',dtype='float32')
        with TemporaryDirectory(prefix='cadence-ui-audio-') as directory:
            directory=Path(directory)
            reference=directory/'reference.wav'
            changed=directory/'changed.wav'
            voice=directory/'tts.wav'
            sf.write(reference,np.concatenate([source,np.zeros(round(rate*.35)),source,np.zeros(round(rate*.35))]),rate)
            sf.write(changed,np.concatenate([source,np.zeros(rate*4),source,np.zeros(round(rate*.3))]),rate)
            sf.write(voice,source,rate)
            with serve(app) as client:
                env={**os.environ,'CADENCE_BROWSER_URL':str(client.base_url).rstrip('/'),
                     'CADENCE_MIC_WAV':str(reference),'CADENCE_DEVIANT_WAV':str(changed),
                     'CADENCE_TTS_STUB_WAV':str(voice)}
                child=subprocess.run(['node',str(ROOT/'backend/scripts/integrated_ui_smoke.cjs')],
                    cwd=ROOT,env=env,capture_output=True,text=True,timeout=300)
                if child.returncode:
                    raise RuntimeError('Browser acceptance failed:\n'+child.stdout+'\n'+child.stderr)
                report=json.loads(child.stdout.strip())
            with connect() as db:
                rows=db.execute("SELECT * FROM checkins WHERE profile_id='ui-smoke' ORDER BY time").fetchall()
                sessions=db.execute("SELECT * FROM conversations WHERE profile_id='ui-smoke'").fetchall()
                assert rows and sessions
                assert all(row['feature_scores'] and len(row['feature_scores'])==4 for row in rows)
                assert any(row['triggered'] for row in rows)
                assert any(row['waveform_evidence'] for row in rows)
                assert any(row['state']=='confirmed' for row in sessions)
                report['persisted_checkins']=len(rows)
                report['persisted_confirmed_sessions']=sum(row['state']=='confirmed' for row in sessions)
                report['real_four_feature_storage']=True
                report['experimental_waveform_evidence_stored']=True
        report['database']='isolated local PostgreSQL schema; actual transactions'
        report['selection']='real retrieval/adapter/validation; deterministic provider choice; bounded completion at 3 answers'
        report['selector_calls']=calls
    finally:
        with psycopg.connect(url) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    report['schema_removed']=True
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/private/tmp/cadence-integrated-ui-report.json'))
    args=parser.parse_args()
    print(json.dumps(run(args.output),indent=2))
