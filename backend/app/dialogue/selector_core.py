"""Provider-agnostic structured question SELECTION -- picks an id, does
not write question text. Works with any model that can follow a JSON
schema; provider-specific wiring (Groq, Gemini, ...) lives in sibling
modules that each supply their own default model_call, but all of them
share this prompt, schema, and parsing logic.
"""
import json
from typing import Callable

from app.dialogue.validation import SelectorOutput

SYSTEM_INSTRUCTION = (
    "You are selecting, not writing, a question for a voice health "
    "check-in. You will be given a list of eligible question units (each "
    "with an id, the information it seeks, and its source excerpt), the "
    "patient's latest answer, and a boolean \"opening_question\".\n\n"
    "RULE 1, absolute, checked first: if \"opening_question\" is true, "
    "you MUST set abstain to false and MUST set selected_question_id to "
    "one of the given eligible ids -- pick whichever is the best general "
    "opener for a brand-new daily check-in. There is no patient answer "
    "yet in this case, so leave patient_quote as an empty string; that is "
    "correct and expected, not a reason to abstain. Abstaining when "
    "opening_question is true is always wrong, because it would mean the "
    "conversation never starts.\n\n"
    "RULE 2: otherwise (opening_question is false, there is a real "
    "patient_answer), choose at most one question id from the eligible "
    "list that would gather the most useful missing information. Quote "
    "the exact words from the patient's answer that motivated your "
    "choice, if any -- if you cannot quote the patient's own words, leave "
    "patient_quote as an empty string. If no eligible question is clearly "
    "useful, set abstain to true and leave selected_question_id as an "
    "empty string.\n\n"
    "Never invent a question id, a source, or medical advice -- you are "
    "selecting from the provided list only. Respond with exactly this "
    "JSON shape: "
    '{"selected_question_id": "", "evidence_ids": [], "patient_quote": "", "abstain": false}'
)

# Empty string instead of null for unset fields -- nullable/union types
# aren't uniformly supported across providers' strict JSON-schema modes,
# and this schema needs to work with more than one provider.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_question_id": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "patient_quote": {"type": "string"},
        "abstain": {"type": "boolean"},
    },
    "required": ["selected_question_id", "evidence_ids", "patient_quote", "abstain"],
    "additionalProperties": False,
}


def build_prompt(eligible_units: list[dict], latest_answer: str) -> str:
    unit_summaries = [
        {
            "id": u["id"],
            "information_sought": u["information_sought"],
            "source_excerpt": u["source_excerpt"],
        }
        for u in eligible_units
    ]
    return json.dumps({
        "eligible_questions": unit_summaries,
        "patient_answer": latest_answer,
        "opening_question": latest_answer == "",
    })


def select_question(
    eligible_units: list[dict],
    latest_answer: str,
    model_call: Callable[[str], str],
) -> SelectorOutput:
    """Never raises on a bad model response -- malformed/unparseable
    output is treated the same as abstaining, which the caller falls back
    from safely. A true provider failure (timeout, auth error) is left to
    propagate from model_call to the caller, not swallowed here."""
    if not eligible_units:
        return SelectorOutput(selected_question_id=None, evidence_ids=[], patient_quote=None, abstain=True)

    prompt = build_prompt(eligible_units, latest_answer)
    raw = model_call(prompt)
    try:
        data = json.loads(raw)
        selected = data.get("selected_question_id") or None
        quote = data.get("patient_quote") or None
        return SelectorOutput(
            selected_question_id=selected,
            evidence_ids=list(data.get("evidence_ids", [])),
            patient_quote=quote,
            abstain=bool(data.get("abstain", False)) or selected is None,
        )
    except (json.JSONDecodeError, TypeError, AttributeError):
        return SelectorOutput(selected_question_id=None, evidence_ids=[], patient_quote=None, abstain=True)
