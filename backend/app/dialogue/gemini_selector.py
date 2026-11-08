"""Gemini wiring for question selection -- not the current provider
(Groq is, for now, since a key was available first), but kept ready:
swapping is a one-line default-argument change, same selector_core.
"""
import os

from app.dialogue.selector_core import RESPONSE_SCHEMA, SYSTEM_INSTRUCTION, select_question as _select_question
from app.dialogue.validation import SelectorOutput

MODEL = "gemini-2.0-flash"


def _default_model_call(prompt: str) -> str:
    """Real Gemini call -- isolated import so tests never need the
    google-genai package installed, only invoked if no stub is passed."""
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY to call the real selector.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "system_instruction": SYSTEM_INSTRUCTION,
            "response_mime_type": "application/json",
            "response_schema": RESPONSE_SCHEMA,
        },
    )
    return response.text


def select_question(
    eligible_units: list[dict],
    latest_answer: str,
    model_call=_default_model_call,
) -> SelectorOutput:
    return _select_question(eligible_units, latest_answer, model_call)
