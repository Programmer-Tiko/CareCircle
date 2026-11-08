"""HTTP contract tests; storage tests use a real, opt-in TimescaleDB database."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import sys
import uuid
import os

import httpx
import numpy as np
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api import main as api


@pytest.fixture
def bare_client(monkeypatch):
    monkeypatch.delenv('TIGER_DATA_URL', raising=False)
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    with TestClient(api.create_app()) as client:
        yield client


def test_unconfigured_services_return_clear_503(bare_client):
    assert bare_client.post('/profiles/missing/confirm').status_code == 503
    assert bare_client.post('/speak', json={'text': 'Hello'}).status_code == 503
    assert bare_client.get('/docs').status_code == 200


@pytest.mark.parametrize('text', ['', '   ', 'x' * 5001])
def test_speak_validates_text(bare_client, text):
    assert bare_client.post('/speak', json={'text': text}).status_code == 422


def test_speak_returns_provider_mp3(bare_client, monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'test-only-key')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'stock_voice')
    def post(url, **kwargs):
        assert url == 'https://api.elevenlabs.io/v1/text-to-speech/stock_voice'
        assert kwargs['headers']['xi-api-key'] == 'test-only-key'
        assert kwargs['json']['text'] == 'What happened during that pause?'
        assert kwargs['params']['output_format'] == 'mp3_44100_128'
        return httpx.Response(200, content=b'ID3test-audio', headers={'content-type': 'audio/mpeg'},
                              request=httpx.Request('POST', url))
    monkeypatch.setattr(api.httpx, 'post', post)
    response = bare_client.post('/speak', json={'text': 'What happened during that pause?'})
    assert response.status_code == 200
    assert response.headers['content-type'] == 'audio/mpeg'
    assert response.content == b'ID3test-audio'


@pytest.mark.parametrize('failure,status', [('timeout', 504), ('provider', 502), ('non_audio', 502)])
def test_speak_handles_provider_failure(bare_client, monkeypatch, failure, status):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'test-only-key')
    def post(url, **kwargs):
        if failure == 'timeout':
            raise httpx.ReadTimeout('private provider details')
        return httpx.Response(401 if failure == 'provider' else 200,
                              json={'private': 'test-only-key'}, request=httpx.Request('POST', url))
    monkeypatch.setattr(api.httpx, 'post', post)
    response = bare_client.post('/speak', json={'text': 'Hello'})
    assert response.status_code == status
    assert 'test-only-key' not in response.text


def test_cors_preflight(bare_client):
    response = bare_client.options('/speak', headers={'Origin': 'http://localhost:3000',
                                   'Access-Control-Request-Method': 'POST'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == '*'


def test_failed_commit_does_not_return_success(bare_client, monkeypatch):
    statements = []
    commit_attempted = []

    class FakeDatabase:
        def execute(self, query, *args):
            statements.append(query)
            return self

        def fetchone(self):
            # This legacy check-in has not opted into a conversation.
            if 'FROM conversations' in statements[-1]:
                return None
            return {'time': 'irrelevant', 'note_status': 'awaiting_confirmation'}

    @contextmanager
    def failing_transaction():
        yield FakeDatabase()
        commit_attempted.append(True)
        raise psycopg.OperationalError('private connection details')

    # Exercise get_db's real context-manager teardown and function-scoped
    # dependency: the failed commit must replace the pending success response.
    monkeypatch.setattr(api, 'open_connection', failing_transaction)
    response = bare_client.post('/profiles/demo/confirm')
    assert any(query.startswith('UPDATE checkins') for query in statements)
    assert commit_attempted == [True]
    assert response.status_code == 503
    assert response.json() == {'detail': 'Database operation failed.'}
    assert 'private' not in response.text


@pytest.fixture
def database(monkeypatch):
    url = os.getenv('TEST_TIGER_DATA_URL')
    if not url:
        pytest.skip('Set TEST_TIGER_DATA_URL to a dedicated TimescaleDB database.')
    schema = 'api_test_' + uuid.uuid4().hex
    with psycopg.connect(url) as connection:
        connection.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect():
        return psycopg.connect(url, row_factory=dict_row, options=f'-csearch_path={schema},public')
    with connect() as connection:
        connection.execute(Path(api.__file__).with_name('schema.sql').read_text())
    monkeypatch.setattr(api, 'initialize_database', lambda: None)
    try:
        yield connect
    finally:
        with psycopg.connect(url) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@pytest.fixture
def client_factory(database):
    def create():
        app = api.create_app()
        def db_dependency():
            with database() as connection:
                yield connection
        app.dependency_overrides[api.get_db] = db_dependency
        return TestClient(app)
    return create


def recording(pause):
    source = Path(__file__).parent / 'fixtures' / 'speech_chunk.wav'
    chunk, rate = sf.read(source, dtype='float32')
    audio = np.concatenate([np.zeros(int(.3*rate)), chunk,
                            np.zeros(int(pause*rate)), chunk, np.zeros(int(.3*rate))])
    stream = BytesIO()
    sf.write(stream, audio, rate, format='WAV')
    return stream.getvalue()


def enroll(client, profile='demo', form=False):
    files = [('files', (f'ref{i}.wav', recording(.4+i*.02), 'audio/wav')) for i in range(3)]
    return client.post(f'/profiles/{profile}/enroll' + ('' if form else '?condition=copd'),
                       data={'condition': 'copd'} if form else {}, files=files)


def checkin(client, pause=4.0, profile='demo'):
    return client.post(f'/profiles/{profile}/checkin',
                       files={'file': ('today.wav', recording(pause), 'audio/wav')})


def test_real_audio_workflow_survives_new_app(client_factory, database):
    with client_factory() as client:
        response = enroll(client)
        assert response.status_code == 200, response.text
        assert response.json() == {'status': 'enrolled', 'profile_id': 'demo', 'n_reference_takes': 3}
        assert checkin(client, .42).json()['status'] == 'no_change'
        first = checkin(client)
        assert first.status_code == 200, first.text
        assert first.json()['triggered_question'] is None
    # New application, new connections: persistence must not depend on process state.
    with client_factory() as client:
        second = checkin(client)
        assert second.json()['status'] == 'awaiting_answer'
        assert second.json()['measured']['deviation_from_baseline'] == 'persistent'
        assert second.json()['triggered_question'] == 'What happened during that pause?'
        assert client.post('/profiles/demo/confirm').status_code == 404
        response = client.post('/profiles/demo/answer', json={'answer_text': 'I stopped to catch my breath'})
        assert response.status_code == 200, response.text
        assert response.json()['note']['status'] == 'awaiting_confirmation'
        assert response.json()['note']['unresolved']
        assert response.json()['follow_up_question'] is not None
        assert client.post('/profiles/demo/answer', json={'answer_text': 'duplicate'}).status_code == 404
        assert client.post('/profiles/demo/confirm').json() == {'status': 'confirmed'}
    with database() as db:
        rows = db.execute('SELECT * FROM checkins ORDER BY time').fetchall()
        assert len(rows) == 3
        assert [row['triggered'] for row in rows] == [False, False, True]
        assert rows[-1]['note_status'] == 'confirmed'
        assert rows[-1]['patient_said'] == 'I stopped to catch my breath'
        assert all(row['speaking_rate'] > 0 for row in rows)
        assert db.execute("SELECT count(*) AS n FROM timescaledb_information.hypertables "
                          'WHERE hypertable_schema = current_schema() AND hypertable_name = %s',
                          ('checkins',)).fetchone()['n'] == 1


def test_validation_and_profile_isolation(client_factory, database):
    with client_factory() as client:
        assert enroll(client, form=True).status_code == 200
        assert enroll(client).status_code == 409
        assert checkin(client, profile='missing').status_code == 404
        assert client.post('/profiles/missing/answer', json={'answer_text': 'hello'}).status_code == 404
        assert client.post('/profiles/missing/confirm').status_code == 404
        assert client.post('/profiles/demo/answer', json={'answer_text': 'hello'}).status_code == 404
        assert client.post('/profiles/demo/confirm').status_code == 404
        invalid = client.post('/profiles/demo/checkin', files={'file': ('fake.wav', b'not wav', 'audio/wav')})
        assert invalid.status_code == 400
        stream = BytesIO()
        sf.write(stream, np.zeros(16000), 16000, format='WAV')
        assert client.post('/profiles/demo/checkin', files={'file': ('silent.wav', stream.getvalue())}).status_code == 400
        assert client.post('/profiles/few/enroll?condition=copd',
                           files=[('files', ('a.wav', recording(.4)))]).status_code == 400
        assert enroll(client, profile='other').status_code == 200
        assert checkin(client).status_code == 200
        assert checkin(client, profile='other').json()['triggered_question'] is None
        assert checkin(client).json()['status'] == 'awaiting_answer'
        assert checkin(client, .42).json()['status'] == 'no_change'
        # An older triggered row must not remain answerable after a newer normal check-in.
        assert client.post('/profiles/demo/answer', json={'answer_text': 'hello'}).status_code == 404
    with database() as db:
        assert db.execute('SELECT count(*) AS n FROM profiles').fetchone()['n'] == 2
        assert db.execute('SELECT count(*) AS n FROM checkins').fetchone()['n'] == 4


def test_concurrent_checkins_and_answers_are_serialized(client_factory, database):
    with client_factory() as client:
        assert enroll(client).status_code == 200
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: checkin(client), range(2)))
        assert all(r.status_code == 200 for r in responses)
        assert sorted(r.json()['status'] for r in responses) == ['awaiting_answer', 'no_change']
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post('/profiles/demo/answer',
                                  json={'answer_text': 'I was reading'}), range(2)))
        assert sorted(r.status_code for r in responses) == [200, 404]
    with database() as db:
        rows = db.execute('SELECT time FROM checkins').fetchall()
        assert len(rows) == len({row['time'] for row in rows}) == 2
