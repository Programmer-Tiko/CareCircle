import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.question_cards import classify_answer, get_follow_up_question, get_initial_question


def test_initial_questions_exist_for_both_conditions():
    assert get_initial_question("copd").question_text
    assert get_initial_question("parkinsons").question_text


def test_unknown_condition_raises():
    with pytest.raises(ValueError):
        get_initial_question("unknown")


def test_classify_copd_breath_cue():
    assert classify_answer("copd", "I stopped to catch my breath") == "breath"


def test_classify_parkinsons_speech_difficulty_cue():
    assert classify_answer("parkinsons", "it's hard to get the words out") == "speech_difficulty"


def test_classify_returns_none_when_no_cue_matches():
    assert classify_answer("copd", "I was just distracted by the dog") is None


def test_follow_up_matches_classified_cue():
    cue = classify_answer("copd", "needed to catch my breath there")
    follow_up = get_follow_up_question("copd", cue)
    assert follow_up is not None
    assert "frequent" in follow_up.question_text
