"""Groq wiring for question selection -- temporary provider choice (a key
is already available) ahead of switching to Gemini later. Swapping back
is a one-line change: gemini_selector.py implements the identical
interface against the same selector_core.
"""
import os

from app.dialogue.selector_core import RESPONSE_SCHEMA, SYSTEM_INSTRUCTION, select_question as _select_question
from app.dialogue.validation import SelectorOutput

MODEL = "openai/gpt-oss-20b"  # confirmed available to this account and supports strict json_schema output


def _default_model_call(prompt: str) -> str:
    """Real Groq call -- isolated import so tests never need the groq
    package installed, only invoked if no stub is passed."""
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Set GROQ_API_KEY to call the real selector.")
    # Bounded timeout -- this runs synchronously inside a request handler,
    # under the profile's transaction lock, so a slow provider call must
    # not be allowed to hang a conversation turn indefinitely.
    client = Groq(api_key=api_key, timeout=8.0)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "question_selection", "strict": True, "schema": RESPONSE_SCHEMA},
        },
    )
    return response.choices[0].message.content


def select_question(
    eligible_units: list[dict],
    latest_answer: str,
    model_call=_default_model_call,
) -> SelectorOutput:
    return _select_question(eligible_units, latest_answer, model_call)
