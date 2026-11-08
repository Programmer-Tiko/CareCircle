import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.conversation_adapter import selector_adapter
from app.dialogue.validation import SelectionRejected
import pytest


def _stub(selected_id: str, quote: str, abstain: bool = False):
    def model_call(prompt: str) -> str:
        return json.dumps({
            "selected_question_id": selected_id,
            "evidence_ids": [selected_id] if selected_id else [],
            "patient_quote": quote,
            "abstain": abstain,
        })
    return model_call


def test_opening_turn_selects_from_real_choice_with_no_answer_yet():
    """conversations.py's start() now calls this with turns=[] and
    answer_text='' -- there's no patient text yet to quote, so the model is
    expected to leave patient_quote empty (validation only checks a quote
    against the answer when one was actually given) and still choose a real
    question rather than being forced to abstain just because nothing was
    said yet."""
    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 0.4, "features": {}, "triggered": False},
        "turns": [],
        "answer_text": "",
    }
    result = selector_adapter(context, model_call=_stub("fatigue_level_check", ""))
    assert result["decision"] == "ask"
    assert result["question"]["id"] == "fatigue_level_check"


def test_ask_decision_validates_against_the_real_conversations_selection_model():
    """The actual contract test: conversations.py's Selection.model_validate
    must accept this dict as-is, not just "look right" to this test file."""
    from app.api.conversations import Selection

    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 2.4, "features": {"pause_fraction": 0.3}},
        "turns": [],
        "answer_text": "people keep asking me to repeat myself",
    }
    result = selector_adapter(
        context,
        model_call=_stub("repetition_frequency", "repeat myself"),
    )
    selection = Selection.model_validate(result)  # raises if the shape is wrong
    assert selection.decision == "ask"
    assert selection.resolved is True
    assert selection.question.id == "repetition_frequency"
    assert len(selection.question.sources) >= 1


def test_policy_sourced_unit_gets_a_placeholder_source():
    from app.api.conversations import Selection

    context = {
        "condition": "parkinsons",
        # distraction_check is only reachable when the check-in's own
        # deviation was actually persistent -- see conversation_adapter.py.
        "measured": {"deviation_score": 2.4, "features": {}, "triggered": True},
        "turns": [],
        "answer_text": "the dog interrupted me, nothing wrong",
    }
    result = selector_adapter(context, model_call=_stub("distraction_check", "dog interrupted me"))
    selection = Selection.model_validate(result)
    assert selection.question.sources[0].id == "prototype-dialogue-policy"


def test_already_asked_question_is_excluded_from_eligible_set():
    prior_turn = {"question": {"id": "repetition_frequency", "version": "1", "text": "...", "sources": []},
                  "answer": "it happens often", "answered_at": "2026-01-01T00:00:00Z"}
    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 2.4, "features": {}},
        "turns": [prior_turn],
        "answer_text": "still happens a lot",
    }
    # Stub would select repetition_frequency again if offered it -- but it's
    # already asked, so it must not be in the eligible set passed to the model.
    calls = []

    def spying_model_call(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps({"selected_question_id": "", "evidence_ids": [], "patient_quote": "", "abstain": True})

    with pytest.raises(SelectionRejected):
        selector_adapter(context, model_call=spying_model_call)
    assert all("repetition_frequency" not in c for c in calls) or not calls


def test_model_abstaining_raises_selection_rejected_not_swallowed_here():
    """conversations.py's own try/except is what converts this to abstain --
    the adapter deliberately doesn't duplicate that handling."""
    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 2.4, "features": {}},
        "turns": [],
        "answer_text": "something unclear",
    }
    with pytest.raises(SelectionRejected):
        selector_adapter(context, model_call=_stub("", "", abstain=True))


def test_empty_eligible_set_completes_instead_of_erroring():
    # Marks every corpus unit as already-asked, regardless of how many
    # exist -- deliberately not hardcoding IDs, so this doesn't silently
    # break (or silently stop testing the real exhaustion path) every
    # time the corpus grows.
    from app.dialogue.retrieval import load_corpus

    turns = [
        {"question": {"id": unit["id"]}, "answer": "no", "answered_at": "x"}
        for unit in load_corpus()
        if unit["condition"] == "parkinsons"
    ]
    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 2.4, "features": {}},
        "turns": turns,
        "answer_text": "no",
    }
    result = selector_adapter(context, model_call=_stub("", ""))
    assert result == {"decision": "complete", "resolved": True}


@pytest.mark.parametrize('scores,allowed', [({}, False), ({'pause_fraction': 2.0}, True),
                                          ({'pause_fraction': -2.0}, False)])
def test_measured_z_scores_gate_breath_support(scores, allowed):
    context = {'condition':'parkinsons', 'measured':{'features':{'pause_fraction':.9},
               'feature_scores':scores}, 'turns':[], 'answer_text':'It was difficult'}
    call = _stub('breath_support_phrasing', 'difficult')
    if allowed:
        result = selector_adapter(context, model_call=call)
        assert result['question']['id'] == 'breath_support_phrasing'
    else:
        with pytest.raises(SelectionRejected):
            selector_adapter(context, model_call=call)
