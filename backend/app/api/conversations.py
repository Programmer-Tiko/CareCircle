"""Opt-in durable conversation routes. Selection is an injectable integration seam.

No model-generated note or question is trusted here: the selector adapter must
return a validated Selection. The default abstains and preserves uncertainty.
"""
import math
import os
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.models.personal_baseline import BaselineStats, FEATURE_ORDER, per_feature_deviation
from app.dialogue.conversation_adapter import emergency_selection

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class Source(BaseModel):
    id: Text
    version: Text
    url: str | None = None
    excerpt: str | None = None


class Question(BaseModel):
    id: Text
    version: Text
    text: Text
    sources: list[Source] = Field(min_length=1)


class Selection(BaseModel):
    decision: Literal['ask', 'complete', 'abstain']
    question: Question | None = None
    resolved: bool = False

    @model_validator(mode='after')
    def consistent(self):
        if (self.decision == 'ask') != (self.question is not None):
            raise ValueError('Only ask decisions must include a question.')
        return self


class StartRequest(BaseModel):
    checkin_time: datetime


class TurnAnswer(BaseModel):
    submission_id: UUID
    answer_text: Text | None = None
    skipped: bool = False

    @model_validator(mode='after')
    def explicit_answer_or_skip(self):
        if self.skipped == (self.answer_text is not None):
            raise ValueError('Provide either reviewed answer_text or skipped=true.')
        return self


class Confirmation(BaseModel):
    revision: int = Field(ge=1)


def select_next(context: dict) -> Selection:
    """Replace via app.dependency_overrides[get_selector] with validated adapter."""
    return Selection(decision='abstain')


def get_selector():
    return select_next


def install_routes(app, get_db, locked_profile, classify_measurement):
    Database = Annotated[object, Depends(get_db, scope='function')]
    Selector = Annotated[object, Depends(get_selector)]

    def load(db, profile_id, session_id):
        locked_profile(db, profile_id)
        row = db.execute('SELECT * FROM conversations WHERE session_id = %s AND profile_id = %s FOR UPDATE',
                         (session_id, profile_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Conversation not found.')
        return row

    def snapshot(db, session_id):
        session = db.execute('SELECT * FROM conversations WHERE session_id = %s', (session_id,)).fetchone()
        turns = db.execute('SELECT * FROM conversation_turns WHERE session_id = %s ORDER BY ordinal',
                           (session_id,)).fetchall()
        # Enrich legacy snapshots on read; do not rewrite historic measurements.
        measured = dict(session['measured'])
        measured['deviation_from_baseline'] = classify_measurement(measured.get('deviation_score'), measured.get('triggered'))
        session = {**session, 'measured': measured}
        for turn in turns:
            turn['skipped'] = bool(turn.get('closed_at') and turn.get('answered_at') and turn.get('answer') is None)
        return jsonable_encoder({**session, 'turns': turns})

    @app.post('/profiles/{profile_id}/conversations')
    def start(profile_id: str, body: StartRequest, db: Database, selector: Selector):
        profile = locked_profile(db, profile_id)
        existing = db.execute('SELECT session_id FROM conversations WHERE profile_id = %s AND checkin_time = %s',
                              (profile_id, body.checkin_time)).fetchone()
        if existing:
            return snapshot(db, existing['session_id'])
        row = db.execute('SELECT * FROM checkins WHERE profile_id = %s AND time = %s',
                         (profile_id, body.checkin_time)).fetchone()
        # A check-in no longer has to have crossed the persistent-deviation
        # threshold to open a conversation -- every check-in gets one, so a
        # patient with a typical reading can still say what's on their mind.
        # row['triggered'] still flows into `measured` below and keeps
        # gating the units that are specifically about a flagged deviation
        # (e.g. distraction_check); it just no longer gates whether a
        # conversation exists at all.
        if row is None or row['note_status'] is not None:
            raise HTTPException(409, 'Start requires an unanswered check-in.')
        session_id = uuid4()
        measured = {'deviation_score': row['deviation_score'], 'triggered': bool(row['triggered']),
                    'reference_median': profile['baseline_median'],
                    'deviation_from_baseline': classify_measurement(row['deviation_score'], row['triggered']),
                    'features': {key: row[key] for key in FEATURE_ORDER if row.get(key) is not None}}
        # Prefer the evidence recorded when scoring, not a later baseline.
        scores = row.get('feature_scores')
        if scores is None:
            if all(key in measured['features'] and key in (profile['baseline_median'] or {})
                   and key in (profile['baseline_mad'] or {}) for key in FEATURE_ORDER):
                scores = per_feature_deviation(
                    BaselineStats(median=profile['baseline_median'], mad=profile['baseline_mad']),
                    measured['features'])
            else:
                scores = {}  # Legacy rows cannot invent a missing fourth measurement.
        measured['feature_scores'] = scores
        if row.get('waveform_evidence') is not None:
            measured['waveform_evidence'] = row['waveform_evidence']
        if row.get('phrase_evidence') is not None:
            measured['phrase_evidence'] = row['phrase_evidence']
        if not all(math.isfinite(value) for value in measured['feature_scores'].values()):
            raise HTTPException(409, 'Check-in produced nonfinite feature scores.')
        db.execute('INSERT INTO conversations (session_id, profile_id, checkin_time, measured) VALUES (%s,%s,%s,%s)',
                   (session_id, profile_id, body.checkin_time, Jsonb(measured)))
        # The opening question comes from the same selector/eligible-set
        # mechanism as every follow-up -- not a fixed line of text. With no
        # answer yet to react to, context flags fall back to whatever the
        # measurement itself and an empty answer imply (no situational-
        # distraction signal, no speech-difficulty report yet); units with
        # no preconditions at all (several already exist in the corpus)
        # are picked from genuinely, not just nominally.
        try:
            selection = Selection.model_validate(selector({'condition': profile['condition'],
                'measured': measured, 'turns': [], 'answer_text': ''}))
        except Exception:
            selection = Selection(decision='abstain')
        if selection.question:
            db.execute('INSERT INTO conversation_turns (turn_id, session_id, ordinal, question) VALUES (%s,%s,1,%s)',
                       (uuid4(), session_id, Jsonb(selection.question.model_dump())))
        else:
            # No eligible opening question at all (corpus exhausted or the
            # selector abstained) -- close the conversation immediately with
            # an honest, empty note rather than leaving a question-less
            # active session with nothing to answer.
            state = 'complete' if selection.decision == 'complete' else 'abstained'
            note = {'measured': measured, 'patient_said': [],
                    'unresolved': ['No supported opening question was available for this reading.'],
                    'status': 'awaiting_confirmation'}
            db.execute('UPDATE conversations SET state=%s, note=%s WHERE session_id=%s', (state, Jsonb(note), session_id))
        return snapshot(db, session_id)

    @app.get('/profiles/{profile_id}/conversations/{session_id}')
    def read(profile_id: str, session_id: UUID, db: Database):
        load(db, profile_id, session_id)
        return snapshot(db, session_id)

    @app.post('/profiles/{profile_id}/conversations/{session_id}/turns/{turn_id}/answer')
    def answer(profile_id: str, session_id: UUID, turn_id: UUID, body: TurnAnswer, db: Database, selector: Selector):
        session = load(db, profile_id, session_id)
        turn = db.execute('SELECT * FROM conversation_turns WHERE session_id = %s AND turn_id = %s',
                          (session_id, turn_id)).fetchone()
        if turn is None:
            raise HTTPException(404, 'Turn not found.')
        if turn['answered_at'] is not None or turn.get('closed_at') is not None:
            if (turn['submission_id'] == body.submission_id and turn['answer'] == body.answer_text
                    and bool(turn.get('closed_at')) == body.skipped):
                return snapshot(db, session_id)
            raise HTTPException(409, 'Turn already answered.')
        if session['state'] != 'active':
            raise HTTPException(409, 'Conversation is not accepting answers.')
        duplicate = db.execute('SELECT turn_id FROM conversation_turns WHERE session_id = %s AND submission_id = %s',
                               (session_id, body.submission_id)).fetchone()
        if duplicate:
            raise HTTPException(409, 'Submission ID already used for another turn.')
        profile = locked_profile(db, profile_id)
        history = snapshot(db, session_id)['turns']
        try:
            max_questions=max(1,min(20,int(os.getenv('CADENCE_MAX_QUESTIONS','4'))))
        except ValueError:
            max_questions=4
        budget_reached=len(history)>=max_questions
        safety = emergency_selection(body.answer_text or '')
        if safety is not None:
            # The question budget and an injected/provider selector must never
            # suppress the fixed safety notice. This remains a narrow tripwire.
            selection = Selection.model_validate(safety)
        elif budget_reached:
            # Question budget ends the interview, never asserts clinical resolution.
            selection=Selection(decision='abstain')
        else:
            try:
                selection = Selection.model_validate(selector({'condition': profile['condition'],
                    'measured': session['measured'], 'turns': history, 'answer_text': body.answer_text or ''}))
                if selection.question and any(t['question']['id'] == selection.question.id for t in history):
                    selection = Selection(decision='abstain')
                if selection.decision == 'complete' and (body.skipped or not selection.resolved or any(
                        t['answered_at'] and not t['resolved'] for t in history)):
                    selection = Selection(decision='abstain')
            except Exception:
                # Provider/schema/validation failure never loses the patient's answer.
                selection = Selection(decision='abstain')
        db.execute('UPDATE conversation_turns SET answer=%s, answered_at=clock_timestamp(), resolved=%s, '
                   'closed_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END, '
                   'submission_id=%s, selection=%s WHERE turn_id=%s',
                   (body.answer_text, selection.resolved and not body.skipped, body.skipped,
                    body.submission_id, Jsonb(selection.model_dump()), turn_id))
        if selection.question:
            db.execute('INSERT INTO conversation_turns (turn_id,session_id,ordinal,question) VALUES (%s,%s,%s,%s)',
                       (uuid4(), session_id, turn['ordinal'] + 1, Jsonb(selection.question.model_dump())))
        state = {'ask': 'active', 'complete': 'complete', 'abstain': 'abstained'}[selection.decision]
        answers = [t['answer'] for t in history if t['answered_at'] and t['answer'] is not None]
        if not body.skipped:
            answers.append(body.answer_text)
        skipped = body.skipped or any(t.get('skipped') for t in history)
        note = {'measured': session['measured'], 'patient_said': answers,
                'unresolved': [] if state == 'complete' else [
                    'This check-in reached its question limit; some details remain unclear.' if budget_reached
                    else 'The conversation contains unresolved information.'],
                'status': 'awaiting_confirmation'}
        if skipped:
            note['unresolved'].append('A question was skipped; its answer is unknown.')
        db.execute('UPDATE conversations SET revision=revision+1, state=%s, note=%s WHERE session_id=%s',
                   (state, Jsonb(note), session_id))
        return snapshot(db, session_id)

    @app.post('/profiles/{profile_id}/conversations/{session_id}/confirm')
    def confirm(profile_id: str, session_id: UUID, body: Confirmation, db: Database):
        session = load(db, profile_id, session_id)
        if session['revision'] != body.revision:
            raise HTTPException(409, 'Note revision changed; review it before confirming.')
        if session['state'] not in ('complete', 'abstained', 'confirmed'):
            raise HTTPException(409, 'Answer the outstanding question before confirming.')
        note = {**session['note'], 'status': 'confirmed'}
        db.execute("UPDATE conversations SET state='confirmed', note=%s, confirmed_at=COALESCE(confirmed_at,now()) "
                   'WHERE session_id=%s', (Jsonb(note), session_id))
        return snapshot(db, session_id)
