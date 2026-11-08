import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.selector_core import select_question
from app.dialogue.validation import validate_selection

ELIGIBLE = [
    {"id": "everyday_communication_impact", "information_sought": "everyday_communication_impact",
     "source_excerpt": "...", "question_template": "Where have you noticed that?"},
]


def test_well_formed_stub_response_selects_and_validates():
    def stub(prompt: str) -> str:
        return json.dumps({
            "selected_question_id": "everyday_communication_impact",
            "evidence_ids": ["everyday_communication_impact"],
            "patient_quote": "repeat myself",
            "abstain": False,
        })

    output = select_question(ELIGIBLE, "people keep asking me to repeat myself", model_call=stub)
    result = validate_selection(output, ELIGIBLE, "people keep asking me to repeat myself")
    assert result.rendered_question_text == "Where have you noticed that?"


def test_malformed_json_falls_back_to_abstain_not_a_crash():
    def stub(prompt: str) -> str:
        return "not json at all {{{"

    output = select_question(ELIGIBLE, "some answer", model_call=stub)
    assert output.abstain is True
    assert output.selected_question_id is None


def test_empty_eligible_list_abstains_without_calling_the_model():
    calls = []

    def stub(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps({"selected_question_id": None, "evidence_ids": [], "patient_quote": None, "abstain": True})

    output = select_question([], "some answer", model_call=stub)
    assert output.abstain is True
    assert calls == []  # never called the model for an empty eligible set


def test_model_hallucinating_an_unlisted_id_is_caught_by_validation_not_the_selector():
    def stub(prompt: str) -> str:
        return json.dumps({
            "selected_question_id": "made_up_id",
            "evidence_ids": [],
            "patient_quote": None,
            "abstain": False,
        })

    output = select_question(ELIGIBLE, "some answer", model_call=stub)
    # The selector itself doesn't filter this -- validate_selection does.
    assert output.selected_question_id == "made_up_id"
    import pytest
    from app.dialogue.validation import SelectionRejected
    with pytest.raises(SelectionRejected):
        validate_selection(output, ELIGIBLE, "some answer")
