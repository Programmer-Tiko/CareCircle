"""Source-linked question cards and retrieval. Deterministic lookup only --
no generative model required for the live app to function. Matches the
brief's condition-specific table exactly.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class QuestionCard:
    condition: str
    cue: str
    question_text: str
    source: str
    review_status: str


QUESTION_CARDS: list[QuestionCard] = [
    QuestionCard(
        condition="copd",
        cue="initial",
        question_text="What happened during that pause?",
        source="VoiceShift dialogue policy, design decision table",
        review_status="prototype",
    ),
    QuestionCard(
        condition="copd",
        cue="breath",
        question_text="Is that more frequent than usual, and what were you doing at the time?",
        source="ALA COPD Action Plan and Management Tools",
        review_status="prototype",
    ),
    QuestionCard(
        condition="parkinsons",
        cue="initial",
        question_text="What happened there?",
        source="VoiceShift dialogue policy, design decision table",
        review_status="prototype",
    ),
    QuestionCard(
        condition="parkinsons",
        cue="speech_difficulty",
        question_text="Where have you noticed that, and has being understood in everyday conversations changed?",
        source="VoiceShift dialogue policy, design decision table",
        review_status="prototype",
    ),
]

_CARD_INDEX = {(card.condition, card.cue): card for card in QUESTION_CARDS}

# Keyword classification of the patient's free-text answer to the initial
# question. Deliberately simple and explainable -- a real NLU/LLM layer
# could replace this, constrained to fall back to these exact cards.
_BREATH_KEYWORDS = ("breath", "breathing", "winded", "out of air")
_SPEECH_DIFFICULTY_KEYWORDS = ("hard to", "difficult", "words", "trouble speaking", "slur")


def get_initial_question(condition: str) -> QuestionCard:
    card = _CARD_INDEX.get((condition, "initial"))
    if card is None:
        raise ValueError(f"No initial question card for condition: {condition}")
    return card


def classify_answer(condition: str, answer_text: str) -> str | None:
    text = answer_text.lower()
    if condition == "copd" and any(kw in text for kw in _BREATH_KEYWORDS):
        return "breath"
    if condition == "parkinsons" and any(kw in text for kw in _SPEECH_DIFFICULTY_KEYWORDS):
        return "speech_difficulty"
    return None


def get_follow_up_question(condition: str, cue: str) -> QuestionCard | None:
    return _CARD_INDEX.get((condition, cue))
