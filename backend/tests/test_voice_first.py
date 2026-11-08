"""Voice transport and durable semantics. Providers are injected, never called live."""
from io import BytesIO
from uuid import uuid4

import numpy as np
import pytest
import soundfile as sf
from psycopg.types.json import Jsonb

from test_conversations import conversation_clients
from test_speech import client, wav
from app.api import speech
from app.audio.phrase_alignment import TranscriptionResult, WordTimestamp
from test_api import bare_client
import httpx
from pathlib import Path


def test_transcript_always_requires_review_and_empty_model_output_is_rejected(client):
    client.app.dependency_overrides[speech.get_transcriber] = lambda: lambda path: TranscriptionResult(
        [WordTimestamp('Perhaps', 0, .2, .99)], .99, 'injected-local')
    response = client.post('/transcribe', files={'file': ('answer.wav', wav())})
    assert response.status_code == 200
    assert response.json()['needs_review'] is True
    assert response.json()['text'] == 'Perhaps'
    client.app.dependency_overrides[speech.get_transcriber] = lambda: lambda path: TranscriptionResult([], 0, 'stub')
    assert client.post('/transcribe', files={'file': ('answer.wav', wav())}).status_code == 422


@pytest.mark.parametrize('samples', [np.zeros(16000), np.ones(16000), np.full(16000, np.nan)])
def test_silent_distorted_or_invalid_recordings_never_reach_model(client, samples):
    def forbidden(path):
        raise AssertionError('Invalid input reached ASR.')
    client.app.dependency_overrides[speech.get_transcriber] = lambda: forbidden
    buffer = BytesIO()
    sf.write(buffer, samples, 16000, format='WAV', subtype='FLOAT')
    assert client.post('/transcribe', files={'file': ('answer.wav', buffer.getvalue())}).status_code == 422


@pytest.mark.parametrize('score,triggered,expected', [(0.5, False, 'usual'), (3.2, False, 'elevated'), (3.2, True, 'persistent')])
def test_classification_survives_start_reload_history_and_legacy_snapshots(conversation_clients, score, triggered, expected):
    factory, stamp = conversation_clients
    with factory.connect() as db:
        db.execute('UPDATE checkins SET deviation_score=%s, triggered=%s WHERE profile_id=%s', (score, triggered, 'demo'))
    with factory() as app:
        session = app.post('/profiles/demo/conversations', json={'checkin_time': stamp.isoformat()}).json()
        root = '/profiles/demo/conversations/' + session['session_id']
        assert session['measured']['deviation_from_baseline'] == expected
        assert app.get(root).json()['measured']['deviation_from_baseline'] == expected
        assert app.get('/profiles/demo/history').json()['checkins'][0]['measured']['deviation_from_baseline'] == expected
        # A pre-feature conversation contains only its stored score and trigger.
        measured = {k: v for k, v in session['measured'].items() if k != 'deviation_from_baseline'}
        with factory.connect() as db:
            db.execute('UPDATE conversations SET measured=%s WHERE session_id=%s', (Jsonb(measured), session['session_id']))
        assert app.get(root).json()['measured']['deviation_from_baseline'] == expected
        finished = app.post(root + '/finish', json={'revision': 0}).json()
        assert finished['measured']['deviation_from_baseline'] == expected


def test_skip_is_explicit_idempotent_and_never_fabricates_patient_words(conversation_clients):
    factory, stamp = conversation_clients
    with factory() as app:
        session = app.post('/profiles/demo/conversations', json={'checkin_time': stamp.isoformat()}).json()
        root = '/profiles/demo/conversations/' + session['session_id']
        turn_id = session['turns'][0]['turn_id']
        body = {'submission_id': str(uuid4()), 'skipped': True}
        skipped = app.post(root + '/turns/' + turn_id + '/answer', json=body)
        assert skipped.status_code == 200, skipped.text
        value = skipped.json()
        assert value['turns'][0]['skipped'] and value['turns'][0]['answer'] is None
        assert value['note']['patient_said'] == []
        assert any('skipped' in line for line in value['note']['unresolved'])
        assert not value['turns'][0]['resolved']
        assert app.post(root + '/turns/' + turn_id + '/answer', json=body).json() == value
        assert len({t['question']['id'] for t in value['turns']}) == len(value['turns'])
        if value['state'] == 'active':
            value = app.post(root + '/finish', json={'revision': value['revision']}).json()
        assert value['note']['patient_said'] == []
        assert app.post(root + '/confirm', json={'revision': value['revision']}).json()['state'] == 'confirmed'


@pytest.mark.parametrize('extra', [{}, {'skipped': True, 'answer_text': 'Not spoken'}, {'answer_text': ''}])
def test_answer_requires_reviewed_text_or_explicit_skip(conversation_clients, extra):
    factory, stamp = conversation_clients
    with factory() as app:
        session = app.post('/profiles/demo/conversations', json={'checkin_time': stamp.isoformat()}).json()
        url = '/profiles/demo/conversations/' + session['session_id'] + '/turns/' + session['turns'][0]['turn_id'] + '/answer'
        assert app.post(url, json={'submission_id': str(uuid4()), **extra}).status_code == 422


@pytest.mark.parametrize('status', [401, 402, 404, 429])
def test_tts_provider_errors_are_actionable_without_private_details(bare_client, monkeypatch, status):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'fake-test-only')
    def provider(url, **kwargs):
        return httpx.Response(status, json={'detail': 'private provider details'}, request=httpx.Request('POST', url))
    monkeypatch.setattr('app.api.main.httpx.post', provider)
    response = bare_client.post('/speak', json={'text': 'A fictional question.'})
    assert response.status_code == 502
    assert f'HTTP {status}' in response.json()['detail']
    assert 'private provider' not in response.text and 'fake-test-only' not in response.text


def test_question_simulation_requires_explicit_demo_mode():
    from scripts.run_voice import create_voice_app, question_demo_selector
    from app.api.conversations import get_selector
    from fastapi.testclient import TestClient
    live = create_voice_app()
    assert live.dependency_overrides[get_selector]() is not question_demo_selector
    assert TestClient(live).get('/capabilities').json()['question_selection'] == 'unavailable'
    demo = create_voice_app(offline_demo=True)
    assert demo.dependency_overrides[get_selector]() is question_demo_selector
    assert TestClient(demo).get('/capabilities').json()['question_selection'] == 'offline-demo'


def test_reference_acceptance_runs_real_pipeline_without_database_or_retaining_raw_audio(bare_client):
    audio = (Path(__file__).parent / 'fixtures/speech_chunk.wav').read_bytes()
    response = bare_client.post('/reference/validate', files={'file': ('reference.wav', audio)})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['status'] == 'accepted' and value['persisted'] is False
    assert set(value['features']) == {'pause_fraction', 'longest_internal_gap', 'speaking_rate', 'mean_speech_segment_duration'}
    assert value['features']['speaking_rate'] > 0
    # Successful processing does not enroll a profile or return raw audio.
    assert 'audio' not in value and 'profile_id' not in value


def test_reference_rejection_preserves_acceptance_rules(bare_client, monkeypatch):
    invalid = bare_client.post('/reference/validate', files={'file': ('reference.wav', b'not a wav')})
    assert invalid.status_code == 400
    silence = BytesIO()
    sf.write(silence, np.zeros(32000), 16000, format='WAV')
    assert bare_client.post('/reference/validate', files={'file': ('reference.wav', silence.getvalue())}).status_code == 400
    monkeypatch.setattr(speech, 'phrase_evidence', lambda path: {
        'status': 'available', 'phrase_match': 'mismatched', 'observed_tokens': ['different', 'passage']})
    audio = (Path(__file__).parent / 'fixtures/speech_chunk.wav').read_bytes()
    mismatch = bare_client.post('/reference/validate?verify_passage=true', files={'file': ('reference.wav', audio)})
    assert mismatch.status_code == 422 and 'Passage verification did not pass' in mismatch.json()['detail']


def test_personal_reference_survives_profile_conversation_and_history(conversation_clients):
    factory, stamp = conversation_clients
    with factory() as client:
        reference = client.get('/profiles/demo').json()['baseline_median']
        session = client.post('/profiles/demo/conversations', json={'checkin_time': stamp.isoformat()}).json()
        assert session['measured']['reference_median'] == reference
        history = client.get('/profiles/demo/history').json()
        assert history['checkins'][0]['measured']['reference_median'] == reference
