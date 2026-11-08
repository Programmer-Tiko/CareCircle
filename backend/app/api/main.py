"""Run from backend: uvicorn app.api.main:app --reload --port 8000."""
from contextlib import asynccontextmanager, contextmanager
import math
import os
from pathlib import Path
import re
from app.api.conversations import get_selector, install_routes
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, StringConstraints
import soundfile as sf

from app.dialogue.conversation_adapter import selector_adapter
from app.passage import PASSAGE_SYLLABLE_COUNT
from app.models.personal_baseline import BaselineStats, PersistentDeviationTracker, fit_baseline, FEATURE_ORDER, per_feature_deviation
from app.audio.observation_reference import fit_observation_reference, compare_observations
from app.pipeline import build_take_from_audio, evaluate_checkin, process_answer

load_dotenv(Path(__file__).resolve().parents[2] / '.env')
DEVIATION_THRESHOLD = 2.0
REQUIRED_CONSECUTIVE = 2
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
Condition = Literal['copd', 'parkinsons']
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
router = APIRouter()


def open_connection():
    url = os.getenv('TIGER_DATA_URL')
    if not url:
        raise HTTPException(503, 'Set TIGER_DATA_URL to a TimescaleDB/PostgreSQL connection string.')
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)


def initialize_database():
    with open_connection() as db:
        db.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))


def get_db():
    # Connection context commits on success, rolls back on any failed request.
    with open_connection() as db:
        yield db


# Commit before sending a success response, so commit failures can return 503.
Database = Annotated[psycopg.Connection, Depends(get_db, scope='function')]


def locked_profile(db, profile_id):
    profile = db.execute('SELECT * FROM profiles WHERE profile_id = %s FOR UPDATE',
                         (profile_id,)).fetchone()
    if profile is None:
        raise HTTPException(404, 'Profile is not enrolled.')
    return profile


def latest_checkin(db, profile_id):
    return db.execute('SELECT * FROM checkins WHERE profile_id = %s ORDER BY time DESC LIMIT 1',
                      (profile_id,)).fetchone()


@contextmanager
def audio_path(upload):
    try:
        with TemporaryDirectory(prefix='voiceshift-') as directory:
            path = Path(directory) / 'take.wav'
            size = 0
            with path.open('wb') as target:
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, 'WAV upload exceeds 20 MiB.')
                    target.write(chunk)
            try:
                info = sf.info(path)
                if info.format not in ('WAV', 'WAVEX') or info.frames == 0:
                    raise ValueError('Expected a nonempty WAV recording.')
            except (ValueError, sf.LibsndfileError):
                raise HTTPException(400, 'Upload a valid, nonempty WAV recording.') from None
            try:
                yield str(path)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from None
    finally:
        upload.file.close()



def require_matching_phrase(path):
    from app.api.speech import phrase_evidence
    evidence = phrase_evidence(path)
    if evidence['status'] != 'available':
        raise HTTPException(503, 'Phrase verification is unavailable; use typed capture settings or configure local ASR.')
    if evidence.get('phrase_match') != 'matched':
        raise HTTPException(422, 'The transcript could not verify the fixed passage. Listen to your take and record the passage again, or explicitly disable optional verification.')
    return evidence


@router.post('/profiles/{profile_id}/enroll')
def enroll(profile_id: str, db: Database,
           files: Annotated[list[UploadFile], File()],
           condition: Annotated[Condition | None, Query()] = None,
           form_condition: Annotated[Condition | None, Form(alias='condition')] = None,
           verify_passage: Annotated[bool, Query()] = False,
           experimental: Annotated[bool, Query()] = False):
    try:
        chosen_condition = form_condition or condition
        if chosen_condition is None:
            raise HTTPException(400, 'Provide condition: copd or parkinsons.')
        if condition and form_condition and condition != form_condition:
            raise HTTPException(400, 'Form and query conditions disagree.')
        if len(files) < 3 or len(files) > 5:
            raise HTTPException(400, 'Provide 3–5 clean reference WAV recordings.')
        takes = []
        waveform_takes = []
        for upload in files:
            with audio_path(upload) as path:
                if verify_passage:
                    require_matching_phrase(path)
                takes.append(build_take_from_audio(path, PASSAGE_SYLLABLE_COUNT))
                if experimental:
                    from app.audio.prosody_features import extract_prosody_features
                    waveform_takes.append(extract_prosody_features(path))
        baseline = fit_baseline(takes)
        try:
            db.execute('INSERT INTO profiles (profile_id, condition, baseline_median, baseline_mad) '
                       'VALUES (%s, %s, %s, %s)',
                       (profile_id, chosen_condition, Jsonb(baseline.median), Jsonb(baseline.mad)))
            if experimental:
                reference = fit_observation_reference(waveform_takes)
                db.execute('UPDATE profiles SET waveform_baseline=%s WHERE profile_id=%s',
                           (Jsonb(reference),profile_id))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, 'Profile is already enrolled.') from None
        return {'status': 'enrolled', 'profile_id': profile_id, 'n_reference_takes': len(takes)}
    finally:
        for upload in files:
            upload.file.close()


@router.post('/profiles/{profile_id}/checkin')
def checkin(profile_id: str, db: Database, file: Annotated[UploadFile, File()],
            experimental: Annotated[bool, Query()] = False,
            verify_passage: Annotated[bool, Query()] = False):
    profile = locked_profile(db, profile_id)
    if any(feature not in (profile['baseline_median'] or {}) or
           feature not in (profile['baseline_mad'] or {}) for feature in FEATURE_ORDER):
        raise HTTPException(409, 'Profile uses an older feature baseline; enroll a new profile with four reference features.')
    baseline = BaselineStats(median=profile['baseline_median'], mad=profile['baseline_mad'])
    history = db.execute('SELECT deviation_score FROM checkins WHERE profile_id = %s '
                         'ORDER BY time DESC LIMIT %s', (profile_id, REQUIRED_CONSECUTIVE)).fetchall()
    tracker = PersistentDeviationTracker(DEVIATION_THRESHOLD, REQUIRED_CONSECUTIVE)
    for row in reversed(history):
        tracker.observe(row['deviation_score'])
    with audio_path(file) as path:
        phrase = require_matching_phrase(path) if verify_passage else None
        result = evaluate_checkin(path, baseline, tracker, profile['condition'], PASSAGE_SYLLABLE_COUNT)
        take = build_take_from_audio(path, PASSAGE_SYLLABLE_COUNT)
        waveform_evidence = None
        if experimental:
            from app.audio.prosody_features import extract_prosody_features
            waveform_evidence = extract_prosody_features(path)
            waveform_evidence['personal_reference'] = compare_observations(waveform_evidence,profile.get('waveform_baseline'))
    feature_scores = per_feature_deviation(baseline, take)
    if not all(math.isfinite(v) for v in [*take.values(), *feature_scores.values(), result.deviation_score]):
        raise HTTPException(400, 'Recording produced invalid measurements.')
    # Timestamp also identifies the row for answer/confirm. The profile lock and
    # monotonic timestamp prevent ties even when transactions start out of order.
    inserted = db.execute('INSERT INTO checkins (time, profile_id, pause_fraction, longest_internal_gap, '
               'speaking_rate, mean_speech_segment_duration, feature_scores, waveform_evidence, phrase_evidence, deviation_score, triggered, question_text) '
               "VALUES (GREATEST(clock_timestamp(), (SELECT max(time) + interval '1 microsecond' "
               'FROM checkins WHERE profile_id = %s)), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING time',
               (profile_id, profile_id, take['pause_fraction'], take['longest_internal_gap'],
                take['speaking_rate'], take['mean_speech_segment_duration'], Jsonb(feature_scores),
                Jsonb(waveform_evidence) if waveform_evidence is not None else None,
                Jsonb(phrase) if phrase is not None else None, result.deviation_score, result.triggered, result.question_text)).fetchone()
    return {'profile_id': profile_id, 'checkin_time': inserted['time'],
            'measured': {'features': take, 'feature_scores': feature_scores,
                         'waveform_evidence': waveform_evidence, 'phrase_evidence': phrase,
                         'deviation_score': result.deviation_score,
                         'deviation_from_baseline': 'persistent' if result.triggered else
                         ('elevated' if result.deviation_score >= DEVIATION_THRESHOLD else 'usual')},
            'triggered_question': result.question_text,
            'status': 'awaiting_answer' if result.triggered else 'no_change'}


def reject_conversation_owned(db, profile_id, checkin_time):
    if db.execute('SELECT session_id FROM conversations WHERE profile_id=%s AND checkin_time=%s',
                  (profile_id, checkin_time)).fetchone():
        raise HTTPException(409, 'Use the conversation turn endpoints for this check-in.')


class AnswerRequest(BaseModel):
    answer_text: Text


@router.post('/profiles/{profile_id}/answer')
def answer(profile_id: str, body: AnswerRequest, db: Database):
    profile = locked_profile(db, profile_id)
    row = latest_checkin(db, profile_id)
    if row is None or not row['triggered'] or row['note_status'] is not None:
        raise HTTPException(404, 'No pending question to answer.')
    reject_conversation_owned(db, profile_id, row['time'])
    note, follow_up = process_answer(profile['condition'], row['deviation_score'], body.answer_text,
                                     feature_scores=row.get('feature_scores'))
    db.execute('UPDATE checkins SET patient_said = %s, note_status = %s '
               'WHERE profile_id = %s AND time = %s',
               (note.patient_said, note.status, profile_id, row['time']))
    return {'note': note.to_dict(), 'follow_up_question': follow_up}


@router.post('/profiles/{profile_id}/confirm')
def confirm(profile_id: str, db: Database):
    locked_profile(db, profile_id)
    row = latest_checkin(db, profile_id)
    if row is not None:
        reject_conversation_owned(db, profile_id, row['time'])
    if row is None or row['note_status'] not in ('awaiting_confirmation', 'confirmed'):
        raise HTTPException(404, 'No answered note to confirm.')
    db.execute("UPDATE checkins SET note_status = 'confirmed' WHERE profile_id = %s AND time = %s",
               (profile_id, row['time']))
    return {'status': 'confirmed'}


class SpeakRequest(BaseModel):
    text: Text


@router.post('/speak', response_class=Response,
             responses={200: {'content': {'audio/mpeg': {}}}})
def speak(body: SpeakRequest):
    key = os.getenv('ELEVENLABS_API_KEY')
    if not key:
        raise HTTPException(503, 'Set ELEVENLABS_API_KEY to enable speech synthesis.')
    voice = os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', voice):
        raise HTTPException(503, 'ELEVENLABS_VOICE_ID is invalid.')
    try:
        response = httpx.post('https://api.elevenlabs.io/v1/text-to-speech/' + voice,
                              params={'output_format': 'mp3_44100_128'},
                              headers={'xi-api-key': key, 'Accept': 'audio/mpeg'},
                              json={'text': body.text,
                                    'model_id': os.getenv('ELEVENLABS_MODEL_ID', 'eleven_multilingual_v2')},
                              timeout=30.0)
        response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(504, 'Speech synthesis timed out.') from None
    except httpx.HTTPError:
        raise HTTPException(502, 'Speech synthesis provider request failed.') from None
    if not response.content or not response.headers.get('content-type', '').startswith('audio/'):
        raise HTTPException(502, 'Speech synthesis provider returned no audio.')
    return Response(content=response.content, media_type='audio/mpeg')


@asynccontextmanager
async def lifespan(app):
    if os.getenv('TIGER_DATA_URL'):
        try:
            initialize_database()
        except psycopg.Error:
            raise RuntimeError('Database initialization failed; check TIGER_DATA_URL and TimescaleDB.') from None
    yield


def create_app():
    from app.api.workspace import install_routes as install_workspace
    from app.api.speech import install_routes as install_speech
    application = FastAPI(title='VoiceShift API', lifespan=lifespan)
    application.add_middleware(CORSMiddleware, allow_origins=['*'],
                               allow_methods=['*'], allow_headers=['*'])
    application.include_router(router)
    install_routes(application, get_db, locked_profile)
    install_workspace(application, get_db, locked_profile)
    install_speech(application)
    # The default selector always abstains (conversations.py's own safe
    # default); this wires in the validated RAG adapter so conversations
    # actually ask something beyond the legacy initial question.
    application.dependency_overrides[get_selector] = lambda: selector_adapter

    @application.exception_handler(psycopg.Error)
    async def database_error(request, exc):
        # Never return connection strings, SQL, or patient data from driver errors.
        return JSONResponse(status_code=503, content={'detail': 'Database operation failed.'})

    return application


app = create_app()
