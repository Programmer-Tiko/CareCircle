import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.validation import SelectionRejected, SelectorOutput, validate_selection

UNIT_A = {"id": "a", "question_template": "Question A text?", "source_excerpt": "excerpt a"}
UNIT_B = {"id": "b", "question_template": "Question B text?", "source_excerpt": "excerpt b"}
ELIGIBLE = [UNIT_A, UNIT_B]


def test_valid_selection_renders_the_stored_template():
    output = SelectorOutput(selected_question_id="a", evidence_ids=["a"], patient_quote="word", abstain=False)
    result = validate_selection(output, ELIGIBLE, latest_answer="some word here")
    assert result.unit is UNIT_A
    assert result.rendered_question_text == "Question A text?"


def test_abstain_is_rejected():
    output = SelectorOutput(selected_question_id=None, evidence_ids=[], patient_quote=None, abstain=True)
    with pytest.raises(SelectionRejected):
        validate_selection(output, ELIGIBLE, latest_answer="anything")


def test_selection_outside_eligible_set_is_rejected():
    output = SelectorOutput(selected_question_id="not_eligible", evidence_ids=[], patient_quote=None, abstain=False)
    with pytest.raises(SelectionRejected):
        validate_selection(output, ELIGIBLE, latest_answer="anything")


def test_borrowed_evidence_from_another_question_is_rejected():
    output = SelectorOutput(selected_question_id="a", evidence_ids=["b"], patient_quote=None, abstain=False)
    with pytest.raises(SelectionRejected):
        validate_selection(output, ELIGIBLE, latest_answer="anything")


def test_fabricated_patient_quote_is_rejected():
    output = SelectorOutput(selected_question_id="a", evidence_ids=["a"], patient_quote="never said this", abstain=False)
    with pytest.raises(SelectionRejected):
        validate_selection(output, ELIGIBLE, latest_answer="something completely different")


def test_quote_matching_is_case_insensitive():
    output = SelectorOutput(selected_question_id="a", evidence_ids=["a"], patient_quote="STAIRS", abstain=False)
    result = validate_selection(output, ELIGIBLE, latest_answer="it happens on stairs mostly")
    assert result.unit is UNIT_A
