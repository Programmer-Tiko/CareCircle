"""Real HTTP + local PostgreSQL stress run; no cloud/model calls.

TEST_CONVERSATION_DB_URL=postgresql:///postgres python scripts/stress_conversations.py
Creates and removes an isolated schema. Uses the real corpus, retrieval, adapter,
validation and API, replacing only provider selection with deterministic IDs.
Seeded check-ins isolate this exercise from already-tested audio detection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api import main as api
from app.api.conversations import get_selector
from app.dialogue.conversation_adapter import selector_adapter
from app.dialogue.retrieval import load_corpus, load_corpus_version


def run():
    url = os.environ['TEST_CONVERSATION_DB_URL']
    os.environ['CADENCE_MAX_QUESTIONS']='20'  # Deliberate long-conversation stress override.
    schema = 'conversation_stress_' + uuid4().hex
    corpus_path = Path(api.__file__).parents[1] / 'dialogue' / 'question_corpus.json'
    corpus_hash = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    report = {'corpus_sha256': corpus_hash, 'transport':'real HTTP over localhost', 'storage':'local PostgreSQL, isolated schema',
              'model':'deterministic selection stub; no provider call',
              'checkins':'seeded measurements; audio pipeline not exercised',
              'corpus_version':load_corpus_version(), 'corpus_units':len(load_corpus()), 'scenarios':[]}
    with psycopg.connect(url) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(url, row_factory=dict_row, options=f'-csearch_path={schema},public')
    server = thread = sock = None
    try:
        with connect() as db:
            ddl = Path(api.__file__).with_name('schema.sql').read_text()
            db.execute('\n'.join(line for line in ddl.splitlines() if not line.startswith(
                ('CREATE EXTENSION', 'SELECT create_hypertable'))))
            db.execute("INSERT INTO profiles (profile_id,condition,baseline_median,baseline_mad) VALUES ('stress','parkinsons',%s,%s)",
                       (Jsonb({'pause_fraction':.2,'longest_internal_gap':1.,'speaking_rate':3.,'mean_speech_segment_duration':2.}),
                        Jsonb({'pause_fraction':.1,'longest_internal_gap':.2,'speaking_rate':.35,'mean_speech_segment_duration':.5})))
        def seed():
            with connect() as db:
                return db.execute("INSERT INTO checkins (profile_id,triggered,question_text,deviation_score,"
                    "pause_fraction,longest_internal_gap,speaking_rate,mean_speech_segment_duration) VALUES "
                    "('stress',TRUE,'What happened?',3,.4,1.2,2.3,1.5) RETURNING time").fetchone()['time'].isoformat()
        mode = {'value':'normal'}
        seen_contexts = []
        def model_call(prompt):
            payload = json.loads(prompt)
            ids = [unit['id'] for unit in payload['eligible_questions']]
            chosen = 'distraction_check' if 'distraction_check' in ids else ids[0]
            return json.dumps({'selected_question_id':chosen,'evidence_ids':[chosen],
                               'patient_quote':payload['patient_answer'],'abstain':False})
        def selector(context):
            # Check isolation at the actual selector boundary, not just response JSON.
            latest = context['answer_text'].split(':')[0]
            for turn in context['turns']:
                if turn['answer']:
                    assert turn['answer'].split(':')[0] == latest
            seen_contexts.append(len(context['turns']))
            decision = selector_adapter(context, model_call=model_call)
            if mode['value'] == 'earlier_unresolved' and len(context['turns']) == 1:
                decision['resolved'] = False
            if mode['value'] == 'current_unresolved' and decision['decision'] == 'complete':
                decision['resolved'] = False
            return decision
        app = api.create_app()
        def database():
            with connect() as db:
                yield db
        app.dependency_overrides[api.get_db] = database
        app.dependency_overrides[get_selector] = lambda: selector
        # Disable only startup's cloud/Timescale initialization: local schema was
        # explicitly initialized above. All request transactions use real SQL.
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
        thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Local HTTP server did not start.')
            time.sleep(.01)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=15) as client:
            def post(path, body, status=200):
                response = client.post(path,json=body)
                assert response.status_code == status, (path,response.status_code,response.text)
                return response.json()
            def start():
                return post('/profiles/stress/conversations',{'checkin_time':seed()})
            def root(session):
                return '/profiles/stress/conversations/' + session['session_id']
            def read(session):
                response = client.get(root(session)); assert response.status_code == 200
                return response.json()
            def answer(session, marker, text='My voice is weak and I have trouble speaking; people ask me to repeat myself', submission=None):
                turn = session['turns'][-1]
                assert turn['answered_at'] is None
                body = {'submission_id':submission or str(uuid4()),'answer_text':marker+': '+text}
                path = root(session)+'/turns/'+turn['turn_id']+'/answer'
                result = post(path,body)
                assert result['revision'] == session['revision']+1
                assert post(path,body) == result  # every turn retry must be idempotent
                assert len({t['question']['id'] for t in result['turns']}) == len(result['turns'])
                assert sum(t['answered_at'] is None for t in result['turns']) == (result['state']=='active')
                return result
            # Interleave two independently created check-ins for one profile.
            a, b = start(), start()
            assert a['session_id'] != b['session_id'] and a['checkin_time'] != b['checkin_time']
            post(root(a)+'/turns/'+b['turns'][0]['turn_id']+'/answer',
                 {'submission_id':str(uuid4()),'answer_text':'wrong session'},404)
            shared_submission = str(uuid4())
            for index in range(len(load_corpus())+2):
                old_b = read(b)
                if a['state'] == 'active':
                    a = answer(a,'A',submission=shared_submission if index==0 else None)
                assert read(b) == old_b
                old_a = read(a)
                if b['state'] == 'active':
                    b = answer(b,'B',submission=shared_submission if index==0 else None)
                assert read(a) == old_a
                if a['state'] != 'active' and b['state'] != 'active':
                    break
            for session, marker in ((a,'A'),(b,'B')):
                assert session['state']=='complete' and len(session['turns'])>=10
                assert all(t['answered_at'] and t['resolved'] and t['answer'].startswith(marker+':') for t in session['turns'])
                assert not session['note']['unresolved']
                post(root(session)+'/confirm',{'revision':session['revision']-1},409)
            old_b=read(b)
            assert post(root(a)+'/confirm',{'revision':a['revision']})['state']=='confirmed'
            assert read(b)==old_b
            report['scenarios'].append({'name':'interleaved same-profile sessions','turns':[len(a['turns']),len(b['turns'])],
                'states':[a['state'],b['state']], 'isolated_histories':True,'cross_session_turn_rejected':True,
                'independent_confirmation':True,'idempotent_retries_every_turn':True})
            # Exhaustion after a changed answer excludes remaining corpus units.
            early=start()
            early=answer(early,'EARLY')
            assert early['turns'][-1]['question']['id']=='distraction_check'
            early=answer(early,'EARLY','the dog interrupted me')
            while early['state']=='active' and len(early['turns'])<5:
                early=answer(early,'EARLY','the dog interrupted me')
            assert early['state']=='complete' and len(early['turns'])<5
            report['scenarios'].append({'name':'eligibility exhausted mid-exchange','turns':len(early['turns']),
                'state':early['state'],'unasked_corpus_units':len(load_corpus())-(len(early['turns'])-1)})
            # Attempt completion with an earlier or current explicitly unresolved turn.
            for failure_mode in ('earlier_unresolved','current_unresolved'):
                mode['value']=failure_mode
                session=start()
                for _ in range(len(load_corpus())+2):
                    session=answer(session,failure_mode)
                    if session['state']!='active':
                        break
                assert len(session['turns'])>=10 and session['state']=='abstained'
                assert any(not t['resolved'] for t in session['turns'])
                assert session['note']['unresolved']
                confirmed=post(root(session)+'/confirm',{'revision':session['revision']})
                assert confirmed['note']['unresolved'] and confirmed['state']=='confirmed'
                report['scenarios'].append({'name':failure_mode,'turns':len(session['turns']),
                    'state_before_confirmation':session['state'],'complete_blocked':True,
                    'confirmation_preserves_uncertainty':True})
            with connect() as db:
                report['persisted_sessions']=db.execute('SELECT count(*) AS n FROM conversations').fetchone()['n']
                report['persisted_answers']=db.execute('SELECT count(*) AS n FROM conversation_turns WHERE answered_at IS NOT NULL').fetchone()['n']
                assert report['persisted_sessions']==5
            report['max_selector_history']=max(seen_contexts)
            assert hashlib.sha256(corpus_path.read_bytes()).hexdigest()==corpus_hash, 'Corpus changed during run; retry.'
            report['result']='PASS'
    finally:
        if server:
            server.should_exit=True
        if thread:
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError('HTTP server failed to stop.')
        if sock:
            sock.close()
        with psycopg.connect(url) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    report['test_schema_removed']=True
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=run()
    rendered=json.dumps(result,indent=2)+'\n'
    if args.output:
        args.output.write_text(rendered)
    print(rendered)
