"""Opt-in real-service UI acceptance: Chrome + Tiger + Whisper + Groq + TTS.

Uses an isolated Tiger schema and removes it always. Seeded audio check-ins are
constructed attributed fixtures. Browser microphone is a synthetic speech WAV;
scripted answer text is fictional. No provider stubs are installed.
"""
import argparse
import json
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
from dotenv import load_dotenv
load_dotenv(os.environ.get('CADENCE_PRIVATE_ENV','/Users/AtharvaBadgujar/VoiceRadial/backend/.env'))
os.environ['CADENCE_ASR_ENABLED']='true'
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')
import torch
torch.set_num_threads(2)
import numpy as np
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import soundfile as sf
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/scripts'))
from app.api import main as api
from app.api.conversations import get_selector
from app.dialogue.conversation_adapter import selector_adapter
from verify_live_workflow import serve


def run(output):
    schema='cadence_live_ui_'+uuid4().hex
    report={'scope':'Real Chrome UI, Tiger Cloud, cached local Whisper, Groq, ElevenLabs; no provider stubs',
            'audio':'HTTP setup uses constructed attributed speech fixtures; browser answer microphone uses synthetic Rainbow speech',
            'scripted_answers':'fictional; no real patient interaction', 'events':[], 'selector_calls':[]}
    url=os.environ['TIGER_DATA_URL']
    created=False
    def connect():
        return psycopg.connect(url,row_factory=dict_row,options=f'-csearch_path={schema},public',connect_timeout=15)
    try:
        with psycopg.connect(url,connect_timeout=15) as db:
            db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)));created=True
        with connect() as db:
            db.execute(Path(api.__file__).with_name('schema.sql').read_text())
        app=api.create_app()
        def database():
            with connect() as db:yield db
        def audited_selector(context):
            try:result=selector_adapter(context)
            except Exception as exc:
                report['selector_calls'].append({'status':'error','error_type':type(exc).__name__})
                raise
            report['selector_calls'].append({'status':'ok','decision':result['decision'],
                'question_id':(result.get('question') or {}).get('id')})
            return result
        app.dependency_overrides[api.get_db]=database
        app.dependency_overrides[get_selector]=lambda:audited_selector
        chunk,rate=sf.read(ROOT/'backend/tests/fixtures/speech_chunk.wav',dtype='float32')
        def recording(pause):
            stream=BytesIO();sf.write(stream,np.concatenate([chunk,np.zeros(round(rate*pause)),chunk]),rate,format='WAV')
            return stream.getvalue()
        with serve(app) as client:
            def post(path,**kwargs):
                response=client.post(path,**kwargs);report['events'].append({'path':path,'status':response.status_code})
                assert response.status_code==200,(path,response.status_code)
                return response.json()
            files=[('files',(f'reference{i}.wav',recording(.4+i*.02),'audio/wav')) for i in range(4)]
            post('/profiles/live-ui-proof/enroll',files=files,data={'condition':'parkinsons'})
            for index in range(2):
                checkin=post('/profiles/live-ui-proof/checkin?experimental=true',files={'file':('checkin.wav',recording(4.),'audio/wav')})
                assert checkin['status']==('no_change' if index==0 else 'awaiting_answer')
            caps=client.get('/capabilities').json()
            report['real_capabilities']={'asr_enabled':caps['asr_enabled'],'tts_enabled':caps['tts_enabled']}
            assert caps['asr_enabled'] and caps['tts_enabled'],'Required real-service capability unavailable'
            env={**os.environ,'CADENCE_BROWSER_URL':str(client.base_url).rstrip('/'),
                'CADENCE_MIC_WAV':os.environ.get('CADENCE_LIVE_MIC_WAV','/private/tmp/cadence-rainbow-synthetic.wav')}
            child=subprocess.run(['node',str(ROOT/'backend/scripts/integrated_live_smoke.cjs')],
                cwd=ROOT,env=env,capture_output=True,text=True,timeout=420)
            if child.returncode:
                # Script output contains only fictional UI state and sanitized API errors.
                report['browser_stderr']=child.stderr[-7000:]
                raise RuntimeError('Real-service browser acceptance failed')
            report['browser']=json.loads(child.stdout.strip())
        assert any(call.get('decision')=='ask' for call in report['selector_calls']), 'No actual Groq ask selection succeeded'
        with connect() as db:
            report['stored_confirmed_sessions']=db.execute("SELECT count(*) AS n FROM conversations WHERE state='confirmed'").fetchone()['n']
            report['stored_answered_turns']=db.execute('SELECT count(*) AS n FROM conversation_turns WHERE answered_at IS NOT NULL').fetchone()['n']
            assert report['stored_confirmed_sessions']==1
        report['observed_provider_errors']=[call['error_type'] for call in report['selector_calls'] if call.get('status')=='error']
        report['conversation_completed_naturally']=report['browser']['terminal_state']=='complete'
        report['result']='PASS'
    except Exception as exc:
        report['result']='FAIL';report['error_type']=type(exc).__name__
        raise
    finally:
        if created:
            with psycopg.connect(url,connect_timeout=15) as db:
                db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            report['schema_removed']=True
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/INTEGRATED-LIVE-UI-VERIFICATION.json')
    args=parser.parse_args()
    print(json.dumps(run(args.output),indent=2))
