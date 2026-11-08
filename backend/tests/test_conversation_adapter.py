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
        "measured": {"deviation_score": 2.4, "features": {}},
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
    # Every Parkinson's unit requires conditions not met by an unrecognized,
    # non-distraction, non-medication answer except pd_initial/distraction_check
    # (no preconditions) -- already-asking both exhausts the eligible set.
    turns = [
        {"question": {"id": "distraction_check"}, "answer": "no, nothing", "answered_at": "x"},
        {"question": {"id": "everyday_communication_impact"}, "answer": "no change", "answered_at": "x"},
        {"question": {"id": "repetition_frequency"}, "answer": "no", "answered_at": "x"},
        {"question": {"id": "breath_support_phrasing"}, "answer": "no", "answered_at": "x"},
        {"question": {"id": "volume_awareness"}, "answer": "no", "answered_at": "x"},
        {"question": {"id": "rate_change_direction"}, "answer": "no", "answered_at": "x"},
        {"question": {"id": "swallow_check"}, "answer": "no", "answered_at": "x"},
    ]
    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 2.4, "features": {}},
        "turns": turns,
        "answer_text": "no",
    }
    result = selector_adapter(context, model_call=_stub("", ""))
    assert result == {"decision": "complete", "resolved": True}
