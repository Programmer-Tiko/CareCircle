"""Conversation SQL tests use isolated schemas in an opt-in PostgreSQL database."""
import os
from pathlib import Path
import sys
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api import main as api
from app.api.conversations import get_selector, Selection


@pytest.fixture
def conversation_clients(monkeypatch):
    url = os.getenv('TEST_CONVERSATION_DB_URL')
    if not url:
        pytest.skip('Set TEST_CONVERSATION_DB_URL to a dedicated PostgreSQL test database.')
    schema = 'conversation_test_' + uuid4().hex
    with psycopg.connect(url) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(url, row_factory=dict_row, options=f'-csearch_path={schema},public')
    try:
        with connect() as db:
            # These routes use ordinary PostgreSQL tables. The existing API tests
            # independently require TimescaleDB for the checkins hypertable.
            ddl = Path(api.__file__).with_name('schema.sql').read_text()
            ddl = '\n'.join(line for line in ddl.splitlines() if not line.startswith(
                ('CREATE EXTENSION', 'SELECT create_hypertable')))
            db.execute(ddl)
            db.execute("INSERT INTO profiles (profile_id,condition) VALUES ('demo','parkinsons'),('other','parkinsons')")
            stamp = db.execute("INSERT INTO checkins (profile_id,triggered,question_text,deviation_score,"
                               "pause_fraction,longest_internal_gap,speaking_rate) VALUES "
                               "('demo',TRUE,'What happened?',3,0.4,1.2,2.3) RETURNING time").fetchone()['time']
        monkeypatch.setattr(api, 'initialize_database', lambda: None)
        def factory(selector=None):
            app = api.create_app()
            def dependency():
                with connect() as db:
                    yield db
            app.dependency_overrides[api.get_db] = dependency
            if selector:
                app.dependency_overrides[get_selector] = lambda: selector
            return TestClient(app)
        yield factory, stamp
    finally:
        with psycopg.connect(url) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_selection_contract():
    with pytest.raises(ValueError):
        Selection(decision='ask')
    with pytest.raises(ValueError):
        Selection(decision='complete', question={'id':'q','version':'1','text':'Why?','sources':[{'id':'s','version':'1'}]})


def test_multiturn_restart_retries_and_revision_confirmation(conversation_clients):
    factory, stamp = conversation_clients
    def selector(context):
        assert context['condition'] == 'parkinsons'
        assert context['measured']['features']['pause_fraction'] == .4
        if len(context['turns']) == 1:
            return {'decision':'ask','resolved':True,'question':{'id':'impact','version':'v2',
                'text':'Where have you noticed it?', 'sources':[{'id':'patient-material','version':'2026-11'}]}}
        return {'decision':'complete','resolved':True}
    with factory(selector) as client:
        start = client.post('/profiles/demo/conversations', json={'checkin_time':stamp.isoformat()})
        assert start.status_code == 200, start.text
        session = start.json(); sid = session['session_id']; root = f'/profiles/demo/conversations/{sid}'
        assert client.post('/profiles/demo/conversations', json={'checkin_time':stamp.isoformat()}).json()['session_id'] == sid
        assert client.post('/profiles/demo/answer',json={'answer_text':'bypass'}).status_code == 409
        assert client.post('/profiles/demo/confirm').status_code == 409
        turn = session['turns'][0]['turn_id']; body = {'submission_id':str(uuid4()),'answer_text':'People ask me to repeat myself'}
        url = root + f'/turns/{turn}/answer'
        response = client.post(url,json=body)
        assert response.status_code == 200, response.text
        session = response.json()
        assert session['revision'] == 1 and len(session['turns']) == 2
        assert session['turns'][1]['question']['version'] == 'v2'
        assert session['turns'][0]['answered_at'] and session['turns'][0]['resolved']
        assert client.post(url,json=body).json()['revision'] == 1
        assert client.post(url,json={**body,'answer_text':'changed'}).status_code == 409
        assert client.post(root+'/confirm',json={'revision':1}).status_code == 409
        assert client.get(root.replace('/demo/','/other/')).status_code == 404
    with factory(selector) as client:
        saved = client.get(root).json()
        assert saved['turns'][1]['question']['text'] == 'Where have you noticed it?'
        url = root + '/turns/' + saved['turns'][1]['turn_id'] + '/answer'
        assert client.post(url,json=body).status_code == 409  # reused ID on another turn
        result = client.post(url,json={'submission_id':str(uuid4()),'answer_text':'During dinner'}).json()
        assert result['state'] == 'complete' and result['revision'] == 2
        assert result['note']['patient_said'] == [body['answer_text'],'During dinner']
        assert client.post(root+'/confirm',json={'revision':1}).status_code == 409
        assert client.post(root+'/confirm',json={'revision':2}).json()['state'] == 'confirmed'
        assert client.post(root+'/confirm',json={'revision':2}).json()['note']['status'] == 'confirmed'


def test_selector_failure_preserves_answer_and_uncertainty(conversation_clients):
    factory, stamp = conversation_clients
    def broken(context):
        raise TimeoutError('provider unavailable')
    with factory(broken) as client:
        session = client.post('/profiles/demo/conversations',json={'checkin_time':stamp.isoformat()}).json()
        root = '/profiles/demo/conversations/' + session['session_id']
        url = root + '/turns/' + session['turns'][0]['turn_id'] + '/answer'
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(url,json={'submission_id':str(uuid4()),'answer_text':'Unclear'}),range(2)))
        assert sorted(r.status_code for r in responses) == [200,409]
        saved = client.get(root).json()
        assert saved['state'] == 'abstained'
        assert saved['turns'][0]['answer'] == 'Unclear'
        assert not saved['turns'][0]['resolved']
        assert saved['note']['unresolved']
        assert client.post(root+'/confirm',json={'revision':1}).json()['state'] == 'confirmed'
        assert client.get(root).json()['note']['unresolved']


def test_checkin_exposes_stable_timestamp_for_start(conversation_clients, monkeypatch):
    from types import SimpleNamespace
    factory, stamp = conversation_clients
    monkeypatch.setattr(api, 'evaluate_checkin', lambda *args: SimpleNamespace(
        triggered=True, deviation_score=3.0, question_text='What happened?'))
    monkeypatch.setattr(api, 'build_take_from_audio', lambda *args: {
        'pause_fraction':.4,'longest_internal_gap':1.2,'speaking_rate':2.3})
    with factory() as client:
        fixture = Path(__file__).parent / 'fixtures' / 'speech_chunk.wav'
        result = client.post('/profiles/demo/checkin',files={'file':('take.wav',fixture.read_bytes(),'audio/wav')})
        assert result.status_code == 200, result.text
        response = client.post('/profiles/demo/conversations',json={'checkin_time':result.json()['checkin_time']})
        assert response.status_code == 200, response.text
        assert response.json()['measured']['deviation_score'] == 3.0
