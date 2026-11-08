"""Patient self-check read models, exact-word reports and revision-safe corrections.

Local demo only: these routes intentionally share the existing unauthenticated
API scope. Confirmation is never permission to share with a caregiver.
"""
import importlib.util
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, StringConstraints

from app.models.personal_baseline import FEATURE_ORDER
from app.passage import PASSAGE_ID, PASSAGE_TEXT, PASSAGE_SYLLABLE_COUNT

Text=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=5000)]


class PatientReport(BaseModel):
    report_text: Text


class Finish(BaseModel):
    revision: int=Field(ge=0)


class Correction(BaseModel):
    revision: int=Field(ge=1)
    correction_text: Text


def install_routes(app,get_db,locked_profile,classify_measurement):
    Database=Annotated[object,Depends(get_db,scope='function')]
    repo=Path(__file__).resolve().parents[3]

    def session_response(session, turns):
        measured = dict(session['measured'])
        measured['deviation_from_baseline'] = classify_measurement(measured.get('deviation_score'), measured.get('triggered'))
        return {**session, 'measured': measured, 'turns': [
            {**turn, 'skipped': bool(turn.get('closed_at') and turn.get('answered_at') and turn.get('answer') is None)}
            for turn in turns]}
    app.mount('/frontend',StaticFiles(directory=repo/'frontend',check_dir=False),name='frontend')

    @app.get('/',include_in_schema=False)
    @app.get('/Daily Hello Family.html',include_in_schema=False)
    def home():
        return FileResponse(repo/'Daily Hello Family.html',media_type='text/html',headers={'Cache-Control':'no-cache'})

    @app.get('/favicon.ico',include_in_schema=False)
    def favicon():
        return FileResponse(repo/'frontend/favicon.svg',media_type='image/svg+xml')

    @app.get('/capabilities')
    def capabilities():
        configured=os.getenv('CADENCE_ASR_ENABLED','').strip().lower() in ('1','true','yes','on')
        model=os.getenv('CADENCE_WHISPER_MODEL','base')
        # No model load or network call during capability discovery.
        cache=Path(os.getenv('CADENCE_WHISPER_CACHE',str(Path.home()/'.cache/whisper')))
        ready=configured and importlib.util.find_spec('whisper') is not None and (cache/f'{model}.pt').is_file()
        return {'asr_enabled':bool(ready),
                'asr_reason':None if ready else 'Local speech recognition is not enabled or its optional runtime/checkpoint is unavailable. Typed answers work.',
                'tts_enabled':bool(os.getenv('ELEVENLABS_API_KEY')),
                'tts_provider':'ElevenLabs' if os.getenv('ELEVENLABS_API_KEY') else 'browser-fallback',
                'asr_provider':'local-whisper' if ready else None,
                'question_selection':getattr(app.state,'question_selection_mode',
                    'groq' if os.getenv('GROQ_API_KEY') else 'unavailable'),
                'passage':{'id':PASSAGE_ID,'text':PASSAGE_TEXT,'syllable_count':PASSAGE_SYLLABLE_COUNT},
                'reference_validation':True,
                'experimental_observations':True}

    @app.get('/profiles/{profile_id}')
    def profile(profile_id:str,db:Database):
        row=locked_profile(db,profile_id)
        keys=list((row['baseline_median'] or {}).keys())
        return {'profile_id':profile_id,'condition':row['condition'],'created_at':row['created_at'],
                'baseline_features':keys,'baseline_median':row['baseline_median'],
                'baseline_compatible':all(key in keys for key in FEATURE_ORDER)}

    @app.get('/profiles/{profile_id}/history')
    def history(profile_id:str,db:Database,limit:Annotated[int,Query(ge=1,le=100)]=30):
        profile=locked_profile(db,profile_id)
        rows=db.execute('SELECT ch.*, c.session_id, c.state AS conversation_state, c.revision, c.note '
            'FROM checkins ch LEFT JOIN conversations c ON c.profile_id=ch.profile_id AND c.checkin_time=ch.time '
            'WHERE ch.profile_id=%s ORDER BY ch.time DESC LIMIT %s',(profile_id,limit)).fetchall()
        checkins=[]
        for row in rows:
            measured={'deviation_score':row['deviation_score'],
                'deviation_from_baseline':classify_measurement(row['deviation_score'],row['triggered']),
                'features':{key:row[key] for key in FEATURE_ORDER if row.get(key) is not None},
                'reference_median':profile['baseline_median'],
                'feature_scores':row.get('feature_scores') or {},
                'waveform_evidence':row.get('waveform_evidence'),'phrase_evidence':row.get('phrase_evidence')}
            checkins.append({'time':row['time'],'measured':measured,'triggered':row['triggered'],
                'status':row['conversation_state'] or row['note_status'] or ('awaiting_answer' if row['triggered'] else 'no_change'),
                'conversation':None if not row['session_id'] else {'session_id':row['session_id'],
                    'state':row['conversation_state'],'revision':row['revision'],'note':row['note']}})
        reports=db.execute('SELECT report_id,profile_id,report_text,created_at FROM patient_reports '
                           'WHERE profile_id=%s ORDER BY created_at DESC LIMIT %s',(profile_id,limit)).fetchall()
        return {'profile_id':profile_id,'checkins':checkins,'reports':[{**r,'status':'recorded'} for r in reports]}

    @app.post('/profiles/{profile_id}/reports')
    def report(profile_id:str,body:PatientReport,db:Database):
        locked_profile(db,profile_id)
        row=db.execute('INSERT INTO patient_reports(report_id,profile_id,report_text) VALUES(%s,%s,%s) '
            'RETURNING report_id,profile_id,report_text,created_at',(uuid4(),profile_id,body.report_text)).fetchone()
        return {**row,'status':'recorded'}

    @app.post('/profiles/{profile_id}/conversations/{session_id}/finish')
    def finish(profile_id:str,session_id:UUID,body:Finish,db:Database):
        locked_profile(db,profile_id)
        row=db.execute('SELECT * FROM conversations WHERE session_id=%s AND profile_id=%s FOR UPDATE',
                       (session_id,profile_id)).fetchone()
        if row is None:raise HTTPException(404,'Conversation not found.')
        retry=(row['state']=='abstained' and row['revision']==body.revision+1 and
               (row['note'] or {}).get('session_ended_by_user'))
        if not retry:
            if row['revision']!=body.revision:raise HTTPException(409,'Conversation changed; reload before finishing.')
            if row['state']!='active':raise HTTPException(409,'This conversation has already ended.')
            turns=db.execute('SELECT * FROM conversation_turns WHERE session_id=%s ORDER BY ordinal',
                             (session_id,)).fetchall()
            note={**(row['note'] or {}),'measured':row['measured'],
                  'patient_said':[turn['answer'] for turn in turns if turn['answered_at'] and turn['answer'] is not None],
                  'unresolved':list(dict.fromkeys((row['note'] or {}).get('unresolved',[])+
                      ['The conversation was ended before all questions were answered.'])),
                  'status':'awaiting_confirmation','session_ended_by_user':True}
            db.execute('UPDATE conversation_turns SET closed_at=clock_timestamp() WHERE session_id=%s AND answered_at IS NULL AND closed_at IS NULL',
                       (session_id,))
            db.execute("UPDATE conversations SET state='abstained', revision=revision+1, note=%s WHERE session_id=%s",
                       (Jsonb(note),session_id))
        current=db.execute('SELECT * FROM conversations WHERE session_id=%s',(session_id,)).fetchone()
        turns=db.execute('SELECT * FROM conversation_turns WHERE session_id=%s ORDER BY ordinal',(session_id,)).fetchall()
        return session_response(current,turns)

    @app.post('/profiles/{profile_id}/conversations/{session_id}/correction')
    def correction(profile_id:str,session_id:UUID,body:Correction,db:Database):
        locked_profile(db,profile_id)
        row=db.execute('SELECT * FROM conversations WHERE session_id=%s AND profile_id=%s FOR UPDATE',
                       (session_id,profile_id)).fetchone()
        if row is None:raise HTTPException(404,'Conversation not found.')
        if row['revision']!=body.revision:raise HTTPException(409,'Note revision changed; reload it before correcting.')
        if row['state'] not in ('complete','abstained'):raise HTTPException(409,'Only an unconfirmed note with no outstanding question can be corrected.')
        note={**row['note'],'patient_correction':body.correction_text,'status':'awaiting_confirmation'}
        db.execute('UPDATE conversations SET note=%s, revision=revision+1 WHERE session_id=%s',
                   (Jsonb(note),session_id))
        # Match the durable conversation response contract, preserving original
        # answers and measurements instead of rewriting them as patient edits.
        session=db.execute('SELECT * FROM conversations WHERE session_id=%s',(session_id,)).fetchone()
        turns=db.execute('SELECT * FROM conversation_turns WHERE session_id=%s ORDER BY ordinal',(session_id,)).fetchall()
        return session_response(session,turns)
