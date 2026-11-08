"""UI-facing read models and patient-owned note changes, using actual SQL."""
from test_conversations import conversation_clients
import pytest


@pytest.mark.parametrize('limit', ['1', '4'])
def test_emergency_notice_precedes_budget_and_provider(conversation_clients, monkeypatch, limit):
    from uuid import uuid4
    monkeypatch.setenv('CADENCE_MAX_QUESTIONS', limit)
    factory, stamp = conversation_clients
    calls = []

    def broken_selector(context):
        calls.append(context)
        raise AssertionError('Safety handling must not invoke the selector.')

    with factory(broken_selector) as client:
        session = client.post('/profiles/demo/conversations', json={'checkin_time': stamp.isoformat()}).json()
        root = '/profiles/demo/conversations/' + session['session_id']
        result = client.post(root + '/turns/' + session['turns'][0]['turn_id'] + '/answer', json={
            'submission_id': str(uuid4()), 'answer_text': 'I fell and I cannot get up'})
        assert result.status_code == 200, result.text
        saved = result.json()
        assert saved['state'] == 'active'
        assert saved['turns'][-1]['question']['id'] == 'safety_notice'
        assert 'emergency services' in saved['turns'][-1]['question']['text']
        assert saved['note']['patient_said'] == ['I fell and I cannot get up']
        assert saved['note']['unresolved'] and not saved['turns'][0]['resolved']
        assert client.post(root + '/confirm', json={'revision': 1}).status_code == 409
    assert calls == []


def test_typical_reading_still_accepts_symptom_report(conversation_clients):
    from test_api import recording, checkin
    from uuid import uuid4
    factory, stamp = conversation_clients
    with factory() as client:
        files = [('files', (f'ref{i}.wav', recording(.4 + i * .02), 'audio/wav')) for i in range(3)]
        assert client.post('/profiles/routine/enroll?condition=parkinsons', files=files).status_code == 200
        reading = checkin(client, .42, profile='routine')
        assert reading.status_code == 200
        assert reading.json()['status'] == 'no_change'
        assert reading.json()['measured']['deviation_from_baseline'] == 'usual'
        session = client.post('/profiles/routine/conversations', json={
            'checkin_time': reading.json()['checkin_time']}).json()
        assert session['state'] == 'active' and not session['measured']['triggered']
        root = '/profiles/routine/conversations/' + session['session_id']
        answer = client.post(root + '/turns/' + session['turns'][0]['turn_id'] + '/answer', json={
            'submission_id': str(uuid4()), 'answer_text': 'People ask me to repeat myself'})
        assert answer.status_code == 200, answer.text
        assert answer.json()['note']['patient_said'] == ['People ask me to repeat myself']
        assert answer.json()['state'] == 'active'
        assert answer.json()['turns'][-1]['question']['id'] != session['turns'][0]['question']['id']


def test_missing_groq_keeps_checkin_and_produces_reviewable_uncertainty(conversation_clients):
    from app.dialogue.conversation_adapter import selector_adapter
    factory, stamp = conversation_clients
    with factory(opening_selector=selector_adapter) as client:
        result = client.post('/profiles/demo/conversations', json={'checkin_time': stamp.isoformat()})
        assert result.status_code == 200, result.text
        session = result.json()
        assert session['state'] == 'abstained' and session['turns'] == []
        assert session['note']['unresolved']
        assert session['note']['status'] == 'awaiting_confirmation'
        history = client.get('/profiles/demo/history').json()
        assert history['checkins'][0]['conversation']['state'] == 'abstained'


def test_profile_real_history_and_report_without_trigger(conversation_clients):
    factory,stamp=conversation_clients
    with factory() as client:
        profile=client.get('/profiles/demo')
        assert profile.status_code==200 and profile.json()['baseline_compatible']
        history=client.get('/profiles/demo/history').json()
        assert len(history['checkins'])==1 and history['reports']==[]
        assert history['checkins'][0]['conversation'] is None
        assert client.get('/profiles/missing/history').status_code==404
        saved=client.post('/profiles/demo/reports',json={'report_text':'My voice feels tired even without a triggered question.'})
        assert saved.status_code==200 and saved.json()['status']=='recorded'
        assert client.get('/profiles/demo/history').json()['reports'][0]['report_text']==saved.json()['report_text']
        assert client.get('/profiles/other/history').json()['reports']==[]
        assert client.post('/profiles/demo/reports',json={'report_text':'  '}).status_code==422


def test_note_correction_keeps_evidence_and_requires_reviewed_revision(conversation_clients):
    factory,stamp=conversation_clients
    with factory(lambda context:{'decision':'complete','resolved':True}) as client:
        session=client.post('/profiles/demo/conversations',json={'checkin_time':stamp.isoformat()}).json()
        root='/profiles/demo/conversations/'+session['session_id']
        import uuid
        result=client.post(root+'/turns/'+session['turns'][0]['turn_id']+'/answer',json={
            'submission_id':str(uuid.uuid4()),'answer_text':'Words felt different'}).json()
        corrected=client.post(root+'/correction',json={'revision':1,'correction_text':'I was distracted; I do not know the cause.'})
        assert corrected.status_code==200,corrected.text
        current=corrected.json()
        assert current['revision']==2 and current['note']['patient_said']==result['note']['patient_said']
        assert current['note']['measured']==result['note']['measured']
        assert current['note']['patient_correction'].startswith('I was distracted')
        assert client.post(root+'/confirm',json={'revision':1}).status_code==409
        assert client.post(root+'/correction',json={'revision':1,'correction_text':'stale'}).status_code==409
        assert client.post(root+'/confirm',json={'revision':2}).json()['state']=='confirmed'
        assert client.post(root+'/correction',json={'revision':2,'correction_text':'after approval'}).status_code==409
        assert client.get('/profiles/demo/history').json()['checkins'][0]['conversation']['note']['patient_correction'].startswith('I was distracted')


def test_verification_failure_does_not_create_checkin(conversation_clients,monkeypatch):
    from app.api import speech
    from test_api import checkin
    factory,stamp=conversation_clients
    monkeypatch.setattr(speech,'phrase_evidence',lambda path:{'status':'available','phrase_match':'mismatch'})
    with factory() as client:
        from test_api import recording
        result=client.post('/profiles/demo/checkin?verify_passage=true',files={'file':('reading.wav',recording(.4),'audio/wav')})
        assert result.status_code==422
        assert len(client.get('/profiles/demo/history').json()['checkins'])==1


def test_experimental_enrollment_produces_separate_personal_waveform_reference(conversation_clients):
    from test_api import recording
    factory,stamp=conversation_clients
    with factory() as client:
        files=[('files',(f'ref{i}.wav',recording(.4+i*.02),'audio/wav')) for i in range(3)]
        result=client.post('/profiles/wave/enroll?experimental=true',data={'condition':'parkinsons'},files=files)
        assert result.status_code==200,result.text
        result=client.post('/profiles/wave/checkin?experimental=true',files={'file':('today.wav',recording(.45),'audio/wav')})
        assert result.status_code==200,result.text
        personal=result.json()['measured']['waveform_evidence']['personal_reference']
        assert personal['available'] and not personal['contributes_to_trigger']
        assert personal['f0_spread_semitones']['n_reference_takes']==3


def test_finish_preserves_unanswered_question_and_confirmation_uncertainty(conversation_clients):
    factory,stamp=conversation_clients
    with factory() as client:
        session=client.post('/profiles/demo/conversations',json={'checkin_time':stamp.isoformat()}).json()
        root='/profiles/demo/conversations/'+session['session_id']
        done=client.post(root+'/finish',json={'revision':0})
        assert done.status_code==200,done.text
        current=done.json()
        assert current['state']=='abstained' and current['revision']==1
        assert current['turns'][0]['closed_at'] and current['turns'][0]['answered_at'] is None
        assert current['turns'][0]['question']==session['turns'][0]['question']
        assert current['note']['unresolved']
        assert client.post(root+'/finish',json={'revision':0}).json()==current
        assert client.post(root+'/confirm',json={'revision':1}).json()['note']['unresolved']


def test_question_budget_preserves_last_answer_without_extra_provider_call(conversation_clients,monkeypatch):
    import uuid
    monkeypatch.setenv('CADENCE_MAX_QUESTIONS','2')
    factory,stamp=conversation_clients
    calls=[]
    def selector(context):
        calls.append(context)
        return {'decision':'ask','resolved':True,'question':{'id':'extra','version':'1',
            'text':'Where did you notice that?','sources':[{'id':'prototype','version':'1'}]}}
    with factory(selector) as client:
        session=client.post('/profiles/demo/conversations',json={'checkin_time':stamp.isoformat()}).json()
        root='/profiles/demo/conversations/'+session['session_id']
        for text in ['Words felt different','During dinner']:
            turn=session['turns'][-1]
            result=client.post(root+'/turns/'+turn['turn_id']+'/answer',json={'submission_id':str(uuid.uuid4()),'answer_text':text})
            assert result.status_code==200,result.text
            session=result.json()
        assert len(calls)==1 and len(session['turns'])==2
        assert session['state']=='abstained'
        assert session['note']['patient_said']==['Words felt different','During dinner']
        assert 'question limit' in session['note']['unresolved'][0]


def test_enrollment_verification_identifies_take_and_transcript_without_storing_profile(conversation_clients,monkeypatch):
    from app.api import speech
    from test_api import recording
    factory,stamp=conversation_clients
    evidence=iter([{'status':'available','phrase_match':'matched'},
        {'status':'available','phrase_match':'mismatch','observed_tokens':['a','different','reading'],
         'phrase_match_reason':'Too many words differ from the expected passage.'}])
    monkeypatch.setattr(speech,'phrase_evidence',lambda path:next(evidence))
    with factory() as client:
        files=[('files',(f'ref{i}.wav',recording(.4),'audio/wav')) for i in range(3)]
        response=client.post('/profiles/failed-reference/enroll?verify_passage=true',data={'condition':'parkinsons'},files=files)
        assert response.status_code==422
        detail=response.json()['detail']
        assert 'Reference take 2' in detail and 'a different reading' in detail
        assert client.get('/profiles/failed-reference').status_code==404
