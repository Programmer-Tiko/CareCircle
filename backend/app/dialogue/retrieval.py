"""Metadata filtering plus lexical ranking over the question corpus. No
vector database -- at a few dozen units, filtering by condition/context
flags and ranking by keyword overlap is enough. Add embeddings only if
paraphrase misses actually show up in practice, not preemptively.
"""
import json
import re
from pathlib import Path

_CORPUS_PATH = Path(__file__).with_name("question_corpus.json")

# Deliberately narrow and literal, not a clinical triage system: catches
# an unambiguous disclosure of injury/emergency so the fixed safety notice
# fires every time, not only when a language model happens to notice. A
# prototype safety net, not exhaustive -- documented as such, not implied
# to be complete.
EMERGENCY_KEYWORDS = (
    "i fell", "fell down", "fell and", "hurt myself", "injured", "broke my",
    "can't get up", "cant get up", "bleeding", "call 911", "need an ambulance",
    "hospital now", "chest pain",
)

_DISTRACTION_KEYWORDS = ("dog", "interrupt", "noise", "distract", "phone rang", "someone else")
_SPEECH_DIFFICULTY_KEYWORDS = ("hard to", "difficult", "words", "trouble speaking", "slur", "repeat")
_SPEECH_MOTOR_KEYWORDS = _SPEECH_DIFFICULTY_KEYWORDS + ("breath", "slower", "faster", "quiet", "soft")

_STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "is", "it", "that", "this", "was", "were"}


def contains_emergency_signal(answer_text: str) -> bool:
    text = answer_text.lower()
    return any(kw in text for kw in EMERGENCY_KEYWORDS)


def load_corpus() -> list[dict]:
    data = json.loads(_CORPUS_PATH.read_text())
    return data["units"]


def load_corpus_version() -> str:
    data = json.loads(_CORPUS_PATH.read_text())
    return data["version"]


def compute_context_flags(
    feature_scores: dict[str, float],
    prior_answers: list[str],
    medication_status_known: bool = False,
) -> dict[str, bool]:
    """Derives the named boolean flags units' preconditions/exclusions
    check against, from what's actually available: the per-feature
    deviation scores and the conversation's answers so far. Anything not
    derivable (we don't track medication status yet) defaults to False/
    excluded, rather than guessing.
    """
    latest_answer = prior_answers[-1].lower() if prior_answers else ""
    return {
        "persistent_deviation_triggered": True,
        "measured_pause_fraction_elevated": feature_scores.get("pause_fraction", 0.0) > 1.5,
        "initial_answer_mentions_speech_difficulty": any(
            kw in latest_answer for kw in _SPEECH_DIFFICULTY_KEYWORDS
        ),
        "speech_motor_cue_present": any(kw in latest_answer for kw in _SPEECH_MOTOR_KEYWORDS),
        "answer_indicates_situational_distraction": any(
            kw in latest_answer for kw in _DISTRACTION_KEYWORDS
        ),
        "patient_known_to_take_pd_medication": medication_status_known,
        "medication_status_unknown": not medication_status_known,
    }


def is_eligible(unit: dict, context: dict[str, bool]) -> bool:
    for flag in unit["preconditions"]:
        if not context.get(flag, False):
            return False
    for flag in unit["exclusions"]:
        if context.get(flag, False):
            return False
    return True


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _lexical_overlap(unit: dict, answer_text: str) -> int:
    answer_tokens = _tokenize(answer_text)
    unit_tokens = _tokenize(unit["question_template"]) | _tokenize(unit["information_sought"].replace("_", " "))
    return len(answer_tokens & unit_tokens)


def retrieve_eligible_units(
    condition: str,
    feature_scores: dict[str, float],
    prior_answers: list[str],
    already_asked_ids: set[str],
    medication_status_known: bool = False,
) -> list[dict]:
    """Returns eligible units ranked by lexical overlap with the latest
    answer, most relevant first. Already-asked units are excluded
    entirely -- the selector should never be offered a repeat."""
    context = compute_context_flags(feature_scores, prior_answers, medication_status_known)
    latest_answer = prior_answers[-1] if prior_answers else ""

    candidates = [
        unit
        for unit in load_corpus()
        if unit["condition"] == condition
        and unit["id"] != "safety_notice"  # reachable only via the hard-coded emergency check, never normal selection
        and unit["id"] not in already_asked_ids
        and is_eligible(unit, context)
    ]
    return sorted(candidates, key=lambda u: _lexical_overlap(u, latest_answer), reverse=True)
