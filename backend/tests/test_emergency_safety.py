import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.conversation_adapter import selector_adapter
from app.dialogue.retrieval import contains_emergency_signal, retrieve_eligible_units


def test_emergency_phrase_is_detected():
    assert contains_emergency_signal("I fell down in the kitchen and hurt myself") is True
    assert contains_emergency_signal("it's hard to get words out sometimes") is False


def test_emergency_answer_bypasses_the_model_entirely():
    """model_call must never be invoked -- the safety path is deterministic,
    not dependent on the LLM noticing anything."""
    calls = []

    def spying_model_call(prompt: str) -> str:
        calls.append(prompt)
        raise AssertionError("model should never be called on an emergency answer")

    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 2.4, "features": {}},
        "turns": [],
        "answer_text": "I fell and I think I broke my wrist",
    }
    result = selector_adapter(context, model_call=spying_model_call)
    assert calls == []
    assert result["decision"] == "ask"
    assert result["resolved"] is False
    assert result["question"]["id"] == "safety_notice"
    assert "emergency services" in result["question"]["text"]


def test_safety_notice_validates_against_the_real_selection_model():
    from app.api.conversations import Selection

    context = {
        "condition": "parkinsons",
        "measured": {"deviation_score": 2.4, "features": {}},
        "turns": [],
        "answer_text": "I can't get up, I need help",
    }
    result = selector_adapter(context, model_call=lambda p: (_ for _ in ()).throw(AssertionError()))
    selection = Selection.model_validate(result)
    assert selection.question.id == "safety_notice"


def test_safety_notice_never_appears_in_normal_eligible_sets():
    eligible = retrieve_eligible_units(
        condition="parkinsons", feature_scores={}, prior_answers=["anything at all"], already_asked_ids=set(),
    )
    assert "safety_notice" not in {u["id"] for u in eligible}
