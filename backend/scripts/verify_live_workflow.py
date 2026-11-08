"""Opt-in real-service smoke: isolated Tiger schema, localhost HTTP, Groq and TTS.

Run from repo root with backend/.venv/bin/python. Uses configured backend/.env;
never prints credentials. Uses constructed attributed speech fixtures, not human
passage adherence. Tiny provider calls consume quota. Test schemas are removed.
"""
from contextlib import contextmanager
import json
from io import BytesIO
from pathlib import Path
import socket
import sys
import threading
import time
from uuid import uuid4

import httpx
import numpy as np
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import soundfile as sf
import uvicorn

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.api import main as api
from app.api.conversations import get_selector
from app.dialogue.conversation_adapter import selector_adapter
from app.dialogue.retrieval import load_corpus
import os


@contextmanager
def serve(app):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('HTTP startup failed')
            time.sleep(.01)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120) as client:yield client
    finally:
        server.should_exit=True;thread.join(timeout=15);sock.close()
        if thread.is_alive():raise RuntimeError('HTTP server did not stop')


def run(output):
    schema='cadence_e2e_'+uuid4().hex
    report={'scope':'Real localhost HTTP / Tiger Cloud / Groq / ElevenLabs; constructed real-speech fixtures',
            'browser_microphone':'not exercised','passage_verification':'separate ASR smoke, not wired into API',
            'events':[],'selector_calls':[]}
    def connect():return psycopg.connect(os.environ['TIGER_DATA_URL'],row_factory=dict_row,
        options=f'-csearch_path={schema},public',connect_timeout=15)
    def create_app():
        app=api.create_app()
        def db():
            with connect() as connection:yield connection
        def audited_selector(context):
            try:
                result=selector_adapter(context)
            except Exception as exc:
                report['selector_calls'].append({'status':'error','type':type(exc).__name__})
                raise
            report['selector_calls'].append({'status':'ok','decision':result['decision'],
                'question_id':(result.get('question') or {}).get('id')})
            return result
        app.dependency_overrides[api.get_db]=db
        app.dependency_overrides[get_selector]=lambda:audited_selector
        return app
    def record(pause):
        data,rate=sf.read(Path(__file__).resolve().parents[1]/'tests/fixtures/speech_chunk.wav',dtype='float32')
        stream=BytesIO();sf.write(stream,np.concatenate([data,np.zeros(round(rate*pause)),data]),rate,format='WAV')
        return stream.getvalue()
    created=False
    try:
        with psycopg.connect(os.environ['TIGER_DATA_URL'],connect_timeout=15) as db:
            db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)));created=True
        with connect() as db:
            ddl=Path(api.__file__).with_name('schema.sql').read_text();db.execute(ddl);db.execute(ddl)
        def post(client,path,expected=200,**kwargs):
            response=client.post(path,**kwargs)
            report['events'].append({'path':path,'http_status':response.status_code})
            assert response.status_code==expected,(path,response.status_code)
            return response
        with serve(create_app()) as client:
            files=[('files',(f'ref{i}.wav',record(.4+i*.02),'audio/wav')) for i in range(4)]
            post(client,'/profiles/live-proof/enroll',files=files,data={'condition':'parkinsons'})
            for n in range(2):
                response=post(client,'/profiles/live-proof/checkin?experimental=true',files={'file':('reading.wav',record(4.),'audio/wav')})
                checkin=response.json()
                assert checkin['status']==('no_change' if n==0 else 'awaiting_answer')
                assert len(checkin['measured']['feature_scores'])==4
                assert checkin['measured']['waveform_evidence']['experimental']
            report['checkin_measured']=checkin['measured']
            start={'checkin_time':checkin['checkin_time']}
            session=post(client,'/profiles/live-proof/conversations',json=start).json()
            root='/profiles/live-proof/conversations/'+session['session_id']
            assert post(client,'/profiles/live-proof/conversations',json=start).json()['session_id']==session['session_id']
            for n in range(len(load_corpus())+1):
                if session['state']!='active':break
                pending=session['turns'][-1]
                answer={'submission_id':str(uuid4()),'answer_text':
                    'This is a fictional demonstration. My voice feels quiet and speaking is difficult; people ask me to repeat words.'}
                path=root+'/turns/'+pending['turn_id']+'/answer'
                session=post(client,path,json=answer).json()
                assert post(client,path,json=answer).json()['revision']==session['revision']
            assert session['state'] in ('complete','abstained'), 'Conversation did not terminate'
            assert any(c['decision']=='ask' for c in report['selector_calls'] if c['status']=='ok'), 'No real selection succeeded'
            report['conversation']={'state':session['state'],'turn_count':len(session['turns']),
                'question_ids':[t['question']['id'] for t in session['turns']],
                'unresolved':session['note']['unresolved']}
            post(client,root+'/confirm',expected=409,json={'revision':session['revision']-1})
            confirmed=post(client,root+'/confirm',json={'revision':session['revision']}).json()
            assert post(client,root+'/confirm',json={'revision':session['revision']}).json()==confirmed
            audio=post(client,'/speak',json={'text':'Cadence demonstration. Your note is ready for review.'})
            assert audio.headers['content-type'].startswith('audio/mpeg') and len(audio.content)>1000
            report['tts']={'content_type':audio.headers['content-type'],'bytes':len(audio.content)}
            preflight=client.options('/speak',headers={'Origin':'http://localhost:8080','Access-Control-Request-Method':'POST'})
            assert preflight.headers['access-control-allow-origin']=='*'
            report['browser_cors_preflight']='PASS'
        with serve(create_app()) as client:
            saved=client.get(root);assert saved.status_code==200
            assert saved.json()==confirmed
            report['fresh_app_recovery']='PASS'
        with connect() as db:
            report['db_checkins']=db.execute('SELECT count(*) AS n FROM checkins').fetchone()['n']
            report['db_answered_turns']=db.execute('SELECT count(*) AS n FROM conversation_turns WHERE answered_at IS NOT NULL').fetchone()['n']
            assert db.execute("SELECT count(*) AS n FROM timescaledb_information.hypertables WHERE hypertable_schema=current_schema() AND hypertable_name='checkins'").fetchone()['n']==1
            report['timescale_hypertable']='PASS'
        report['result']='PASS'
    except Exception as exc:
        report['result']='FAIL';report['error_type']=type(exc).__name__
        raise
    finally:
        if created:
            with psycopg.connect(os.environ['TIGER_DATA_URL'],connect_timeout=15) as db:
                db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            report['test_schema_removed']=True
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':run(Path('docs/LIVE-WORKFLOW-VERIFICATION.json'))
