"""Transport tests use injected ASR; no weights, downloads or provider quota."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import sys
from threading import Lock
import time

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api import speech
from app.audio.phrase_alignment import TranscriptionResult, WordTimestamp
from app.passage import PASSAGE_TEXT


def wav():
    return (Path(__file__).parent / 'fixtures/speech_chunk.wav').read_bytes()


@pytest.fixture
def client():
    app = FastAPI()
    speech.install_routes(app)
    with TestClient(app) as client:
        yield client


def test_disabled_and_missing_local_dependencies_return_503(client, monkeypatch):
    monkeypatch.delenv('CADENCE_ASR_ENABLED', raising=False)
    assert client.post('/transcribe',files={'file':('recording.wav',wav())}).status_code == 503
    monkeypatch.setenv('CADENCE_ASR_ENABLED','true')
    monkeypatch.setattr(speech, '_cached_transcriber', lambda model: (_ for _ in ()).throw(ImportError('private details')))
    response = client.post('/transcribe',files={'file':('recording.wav',wav())})
    assert response.status_code == 503 and 'private details' not in response.text


def test_wav_transcription_returns_words_and_temp_file_is_removed(client):
    paths = []
    def model(path):
        paths.append(Path(path))
        assert paths[-1].exists()
        return TranscriptionResult([WordTimestamp('Hello',0,.1,.9),WordTimestamp('there',.2,.3,.8)],.85,'fake-local')
    client.app.dependency_overrides[speech.get_transcriber] = lambda: model
    response = client.post('/transcribe',files={'file':('capture.wav',wav(),'audio/wav')})
    assert response.status_code == 200, response.text
    assert response.json()['text'] == 'Hello there'
    assert response.json()['model_id'] == 'fake-local'
    assert len(response.json()['words']) == 2
    assert not paths[0].exists()


def test_malformed_empty_nonwav_and_oversized_uploads_rejected(client, monkeypatch):
    def forbidden(path):
        raise AssertionError('Invalid upload must never reach ASR.')
    client.app.dependency_overrides[speech.get_transcriber] = lambda: forbidden
    for payload in (b'garbage',b''):
        assert client.post('/transcribe',files={'file':('fake.wav',payload)}).status_code == 400
    buffer = BytesIO()
    sf.write(buffer,np.zeros(100),16000,format='FLAC')
    assert client.post('/transcribe',files={'file':('fake.wav',buffer.getvalue())}).status_code == 400
    monkeypatch.setattr(speech,'MAX_UPLOAD_BYTES',16)
    assert client.post('/transcribe',files={'file':('large.wav',wav())}).status_code == 413


def test_model_failure_and_invalid_evidence_sanitized_and_cleaned(client):
    paths=[]
    def failing(path):
        paths.append(Path(path))
        raise RuntimeError('private model path')
    client.app.dependency_overrides[speech.get_transcriber]=lambda:failing
    response=client.post('/transcribe',files={'file':('capture.wav',wav())})
    assert response.status_code==502 and 'private' not in response.text
    assert not paths[0].exists()
    client.app.dependency_overrides[speech.get_transcriber]=lambda:lambda path:TranscriptionResult([],float('nan'),'fake')
    assert client.post('/transcribe',files={'file':('capture.wav',wav())}).status_code==502


def test_serialized_transcriber_never_enters_model_concurrently():
    guard=Lock(); counts={'active':0,'max':0}
    def model(path):
        with guard:
            counts['active']+=1;counts['max']=max(counts['max'],counts['active'])
        time.sleep(.01)
        with guard:
            counts['active']-=1
        return path
    transcriber=speech._SerializedTranscriber(model)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(transcriber,range(8)))==list(range(8))
    assert counts['max']==1


def test_phrase_evidence_distinguishes_match_from_overall_comparability(monkeypatch):
    tokens=PASSAGE_TEXT.split()
    words=[WordTimestamp(word,i*.2,i*.2+.1,.95) for i,word in enumerate(tokens)]
    monkeypatch.setattr(speech,'get_transcriber',lambda:lambda path:TranscriptionResult(words,.95,'stub'))
    evidence=speech.phrase_evidence('unused')
    assert evidence['available'] and evidence['phrase_match']=='matched'
    assert evidence['comparability']['overall']=='not_assessed'
    assert evidence['comparability']['phrase']=='matched'
    monkeypatch.setattr(speech,'get_transcriber',lambda:lambda path:TranscriptionResult([WordTimestamp('unrelated',0,.1,.95)],.95,'stub'))
    assert speech.phrase_evidence('unused')['phrase_match']=='mismatch'


def test_phrase_unavailability_is_not_a_match(monkeypatch):
    def unavailable():
        raise HTTPException(503,'Disabled')
    monkeypatch.setattr(speech,'get_transcriber',unavailable)
    monkeypatch.delenv('CADENCE_ASR_ENABLED',raising=False)
    evidence=speech.phrase_evidence('unused')
    assert not evidence['available'] and evidence['status']=='disabled'
    assert evidence['phrase_match']=='uncertain'
    assert not evidence['alignment_available']


def test_model_configuration_does_not_accept_paths(monkeypatch):
    monkeypatch.setenv('CADENCE_ASR_ENABLED','true')
    monkeypatch.setenv('CADENCE_WHISPER_MODEL','../../arbitrary')
    with pytest.raises(HTTPException) as error:
        speech.get_transcriber()
    assert error.value.status_code==503


def test_get_transcriber_loads_once_and_rechecks_disabled_configuration(monkeypatch):
    from app.audio import whisper_adapter
    calls=[]
    monkeypatch.setenv('CADENCE_ASR_ENABLED','true')
    monkeypatch.setenv('CADENCE_WHISPER_MODEL','base')
    def factory(model_size):
        calls.append(model_size)
        return lambda path:path
    monkeypatch.setattr(whisper_adapter,'CachedWhisperTranscriber',factory)
    speech._cached_transcriber.cache_clear()
    try:
        assert not calls
        first=speech.get_transcriber()
        assert first is speech.get_transcriber()
        assert calls==['base']
        monkeypatch.setenv('CADENCE_ASR_ENABLED','false')
        with pytest.raises(HTTPException):
            speech.get_transcriber()
        assert calls==['base']
    finally:
        speech._cached_transcriber.cache_clear()


def test_corrupt_phrase_timestamps_are_json_safe_and_not_usable(monkeypatch):
    import json
    words=[WordTimestamp('hello',float('nan'),-1,.95)]
    monkeypatch.setattr(speech,'get_transcriber',lambda:lambda path:TranscriptionResult(words,.95,'stub'))
    evidence=speech.phrase_evidence('unused')
    assert not evidence['alignment_available']
    assert evidence['word_timestamps'][0]['start'] is None
    json.dumps(evidence,allow_nan=False)
