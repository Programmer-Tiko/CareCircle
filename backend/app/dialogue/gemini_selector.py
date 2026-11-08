"""Calls Gemini for structured question SELECTION, not generation -- it
picks an id from the eligible list, it does not write question text. The
actual model call is isolated behind `model_call` so tests never need a
real API key, and wiring a real GEMINI_API_KEY is a one-line change: pass
nothing and the default call is used.
"""
import json
import os
from typing import Callable

from app.dialogue.validation import SelectorOutput

SYSTEM_INSTRUCTION = (
    "You are selecting, not writing, a follow-up question for a voice "
    "health check-in. You will be given a list of eligible question units "
    "(each with an id, the information it seeks, and its source excerpt) "
    "and the patient's latest answer. Choose at most one question id from "
    "the eligible list that would gather the most useful missing "
    "information. Quote the exact words from the patient's answer that "
    "motivated your choice, if any -- if you cannot quote the patient's "
    "own words, leave patient_quote null. If no eligible question is "
    "clearly useful, abstain. Never invent a question id, a source, or "
    "medical advice -- you are selecting from the provided list only."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_question_id": {"type": ["string", "null"]},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "patient_quote": {"type": ["string", "null"]},
        "abstain": {"type": "boolean"},
    },
    "required": ["selected_question_id", "evidence_ids", "patient_quote", "abstain"],
}


def _default_model_call(prompt: str) -> str:
    """Real Gemini call -- isolated import so tests never need the
    google-genai package installed, only invoked if no stub is passed."""
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY to call the real selector.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            "system_instruction": SYSTEM_INSTRUCTION,
            "response_mime_type": "application/json",
            "response_schema": RESPONSE_SCHEMA,
        },
    )
    return response.text


def build_prompt(eligible_units: list[dict], latest_answer: str) -> str:
    unit_summaries = [
        {
            "id": u["id"],
            "information_sought": u["information_sought"],
            "source_excerpt": u["source_excerpt"],
        }
        for u in eligible_units
    ]
    return json.dumps({"eligible_questions": unit_summaries, "patient_answer": latest_answer})


def select_question(
    eligible_units: list[dict],
    latest_answer: str,
    model_call: Callable[[str], str] = _default_model_call,
) -> SelectorOutput:
    """Never raises on a bad model response -- malformed/unparseable
    output is treated the same as abstaining, which the caller falls back
    from safely. The only thing allowed to escalate is a true provider
    failure (timeout, auth error), left to propagate to the caller."""
    if not eligible_units:
        return SelectorOutput(selected_question_id=None, evidence_ids=[], patient_quote=None, abstain=True)

    prompt = build_prompt(eligible_units, latest_answer)
    raw = model_call(prompt)
    try:
        data = json.loads(raw)
        return SelectorOutput(
            selected_question_id=data.get("selected_question_id"),
            evidence_ids=list(data.get("evidence_ids", [])),
            patient_quote=data.get("patient_quote"),
            abstain=bool(data.get("abstain", False)),
        )
    except (json.JSONDecodeError, TypeError, AttributeError):
        return SelectorOutput(selected_question_id=None, evidence_ids=[], patient_quote=None, abstain=True)
