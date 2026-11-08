import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.groq_selector import select_question
from app.dialogue.validation import validate_selection

ELIGIBLE = [
    {"id": "breath_support_phrasing", "information_sought": "breath_support_during_speech",
     "source_excerpt": "...", "question_template": "Do you notice yourself running out of breath partway through a sentence?"},
]


def test_groq_wiring_uses_the_same_core_logic():
    def stub(prompt: str) -> str:
        return json.dumps({
            "selected_question_id": "breath_support_phrasing",
            "evidence_ids": ["breath_support_phrasing"],
            "patient_quote": "run out of breath",
            "abstain": False,
        })

    output = select_question(ELIGIBLE, "I run out of breath by the end of a sentence", model_call=stub)
    result = validate_selection(output, ELIGIBLE, "I run out of breath by the end of a sentence")
    assert result.unit["id"] == "breath_support_phrasing"


def test_real_call_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from app.dialogue.groq_selector import _default_model_call
    import pytest

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        _default_model_call("irrelevant prompt")
