import json
from pathlib import Path
from app.dialogue.retrieval import load_corpus,retrieve_eligible_units,is_eligible
from app.dialogue.conversation_adapter import selector_adapter

NEW={'vocal_fatigue_check','vocal_quality_hoarseness','group_and_noise_communication'}


def test_promoted_communication_sources_are_exact_and_blocked_units_absent():
    corpus=load_corpus();units={unit['id']:unit for unit in corpus}
    assert NEW<=units.keys()
    assert not {'daytime_sleepiness_check','fatigue_physical_vs_mental','morning_off_period_check'}&units.keys()
    chunks=json.loads((Path(__file__).parents[1]/'data/out/knowledge_chunks.json').read_text())
    for key in NEW:
        for span in units[key]['evidence_spans']:
            assert span['source_url']==chunks[span['chunk_index']]['source_url']
            assert span['verbatim_text'] in chunks[span['chunk_index']]['text']


def test_actual_context_rules_gate_new_questions_and_preserve_sources():
    def ids(answer):return {unit['id'] for unit in retrieve_eligible_units('parkinsons',{},[answer],set())}
    assert NEW<=ids('My voice feels weak and people cannot hear me in a noisy room')
    assert not NEW&ids('I have no trouble speaking')
    assert not NEW&ids('The dog interrupted me while I was reading')
    result=selector_adapter({'condition':'parkinsons','measured':{},'turns':[],'answer_text':'My voice feels tired'},
        model_call=lambda prompt:json.dumps({'selected_question_id':'vocal_fatigue_check',
            'evidence_ids':['vocal_fatigue_check'],'patient_quote':'voice feels tired','abstain':False}))
    assert len(result['question']['sources'])>=2
    assert all(source['url'].startswith('https://') and source['excerpt'] for source in result['question']['sources'])


def test_unknown_exclusion_and_explicit_block_fail_closed():
    assert not is_eligible({'blocked':True,'preconditions':[],'exclusions':[]},{})
    assert not is_eligible({'preconditions':[],'exclusions':['unimplemented_flag']},{})
