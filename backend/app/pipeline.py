"""Ties audio, timing features, personal baseline, and dialogue into the
two calls the app actually needs: evaluate a check-in recording, and
process the patient's answer once a question has fired.
"""
from dataclasses import dataclass

from app.audio.timing_features import compute_timing_features
from app.audio.vad import detect_speech_segments
from app.dialogue.note import Note, build_note
from app.dialogue.question_cards import classify_answer, get_follow_up_question, get_initial_question
from app.models.personal_baseline import BaselineStats, PersistentDeviationTracker, deviation_score


@dataclass
class CheckinResult:
    triggered: bool
    deviation_score: float
    question_text: str | None


def build_take_from_audio(wav_path: str, passage_syllable_count: int) -> dict:
    """Shared by enrollment (building reference takes) and check-in
    (scoring a new take against them) -- both need the same three numbers
    from the same VAD + timing-feature pipeline, just used differently.
    """
    segments = detect_speech_segments(wav_path)
    timing = compute_timing_features(segments, passage_syllable_count)
    return {
        "pause_fraction": timing.pause_fraction,
        "longest_internal_gap": timing.longest_internal_gap,
        "speaking_rate": timing.speaking_rate,
    }


def evaluate_checkin(
    wav_path: str,
    baseline: BaselineStats,
    tracker: PersistentDeviationTracker,
    condition: str,
    passage_syllable_count: int,
) -> CheckinResult:
    take = build_take_from_audio(wav_path, passage_syllable_count)
    score = deviation_score(baseline, take)
    persistent = tracker.observe(score)

    question_text = None
    if persistent:
        question_text = get_initial_question(condition).question_text

    return CheckinResult(triggered=persistent, deviation_score=score, question_text=question_text)


def process_answer(condition: str, deviation_score_value: float, answer_text: str) -> tuple[Note, str | None]:
    """Returns the assembled note, plus a follow-up question if the
    patient's answer matched a known cue -- or None if there's nothing
    more to ask and the note is ready as-is.
    """
    cue = classify_answer(condition, answer_text)
    follow_up = get_follow_up_question(condition, cue) if cue else None
    note = build_note(
        deviation_score=deviation_score_value,
        patient_said=answer_text,
        cue_resolved=follow_up is None,
    )
    return note, (follow_up.question_text if follow_up else None)
