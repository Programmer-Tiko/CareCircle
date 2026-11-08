"""Explicit-language eligibility rules; no clinical understanding claim."""
from app.dialogue.retrieval import compute_context_flags, retrieve_eligible_units
import pytest


def flags(*answers):
    return compute_context_flags({},list(answers))


@pytest.mark.parametrize('answer',[
    'I have no trouble speaking', 'I do not have difficulty speaking',
    'My voice is not hoarse', 'I do not slur my words', 'I am tired', 'It is hard to sleep',
    'Maybe my voice is hoarse', "I'm not sure if I have trouble speaking",
    'I used to have trouble speaking', 'I read the words on the screen',
])
def test_denial_uncertainty_and_unrelated_difficulty_do_not_assert_speech(answer):
    assert not flags(answer)['speech_motor_cue_present']


@pytest.mark.parametrize('answer',[
    'My voice is hoarse', 'My voice feels tired', 'My voice sounds weak',
    'It is hard to get words out', 'I have trouble speaking',
    'People ask me to repeat myself', 'People keep asking me to repeat myself', 'People cannot hear me in a noisy room',
    'I run out of breath halfway through a sentence',
])
def test_explicit_speech_reports_are_positive(answer):
    result=flags(answer)
    assert result['speech_motor_cue_present']
    assert result['initial_answer_mentions_speech_difficulty']


def test_explicit_report_memory_survives_neutral_or_uncertain_followups():
    assert flags('My voice is weak','During dinner','I am not sure')['speech_motor_cue_present']
    assert not flags('I have trouble speaking','My speech is back to normal','During dinner')['speech_motor_cue_present']
    assert not flags('My voice is hoarse','I have no trouble speaking')['speech_motor_cue_present']
    assert not flags('My voice is hoarse','No speech problems now')['speech_motor_cue_present']
    assert not flags('My voice is hoarse','My voice is no longer hoarse')['speech_motor_cue_present']
    assert not flags('My voice was weak yesterday but my speech difficulty has resolved now')['speech_motor_cue_present']


def test_last_explicit_clause_wins_without_negation_leaking():
    assert flags('I have no trouble speaking but my voice is hoarse')['speech_motor_cue_present']
    assert not flags('My voice was hoarse but my voice is normal now')['speech_motor_cue_present']


@pytest.mark.parametrize('answer',[
    'People cannot hear me in a noisy room', 'I struggle with background noise in conversations',
    'The dog is sleeping', 'There was noise at dinner', 'The phone rang at work',
    'No one interrupted my recording', 'The dog did not interrupt me',
])
def test_everyday_noise_and_denied_interruption_are_not_recording_distraction(answer):
    result=flags(answer)
    assert not result['recording_interrupted_by_distraction']
    assert not result['answer_indicates_situational_distraction']


@pytest.mark.parametrize('answer',[
    'The dog interrupted me', 'The doorbell rang while I was reading the passage',
    'Someone spoke during the recording', 'Noise distracted me during this take',
])
def test_recording_interruption_is_explicit_and_alias_preserved(answer):
    result=flags(answer)
    assert result['recording_interrupted_by_distraction']
    assert result['answer_indicates_situational_distraction']


def test_everyday_noise_does_not_exclude_communication_question():
    units=retrieve_eligible_units('parkinsons',{},['People cannot hear me in a noisy room'],set())
    assert 'everyday_communication_impact' in {unit['id'] for unit in units}


@pytest.mark.parametrize('answer',[
    'Good', 'good', "I'm good", 'Im good', 'fine', 'okay', 'well',
    'I feel good, nothing unusual', 'all good, no complaints', 'no issues today',
])
def test_wellness_reassurance_is_recognized(answer):
    assert flags(answer)['patient_reports_no_concerns']


@pytest.mark.parametrize('answer',[
    'not good', "I'm not good", "I'm not doing great today", 'pretty tired today honestly',
    'fine I guess', 'my balance has been off',
])
def test_wellness_reassurance_requires_a_real_positive_statement(answer):
    assert not flags(answer)['patient_reports_no_concerns']


def test_wellness_reassurance_closes_out_the_generic_checklist_questions():
    # The actual bug this was written for: "I feel good, nothing unusual"
    # must not leave anything in the generic always-eligible set (fatigue,
    # anxiety, sleep, balance, volume, rate) still offerable -- those are
    # exactly the units with no content-specific precondition to fall back
    # on otherwise.
    units = retrieve_eligible_units('parkinsons', {}, ['I feel good, nothing unusual'], set())
    assert units == []


def test_medication_status_comes_only_from_explicit_known_parameter():
    result=flags('My medication is wearing off')
    assert not result['patient_known_to_take_pd_medication']
    assert result['medication_status_unknown']
    result=compute_context_flags({},[],medication_status_known=True)
    assert result['patient_known_to_take_pd_medication']
    assert not result['medication_status_unknown']
