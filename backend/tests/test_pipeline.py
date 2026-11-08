import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audio.timing_features import compute_timing_features
from app.audio.vad import detect_speech_segments, load_mono_16k
from app.models.personal_baseline import PersistentDeviationTracker, fit_baseline
from app.pipeline import evaluate_checkin, process_answer

SR = 16000


def _real_speech_chunk() -> np.ndarray:
    """A short clip of real recorded speech, not a synthetic tone -- Silero
    VAD is a neural model trained on real speech and correctly rejects a
    pure sine wave as non-speech, so fixtures need actual speech audio.
    """
    source = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "speech_chunk.wav"
    data, sr = sf.read(source, dtype="float32")
    assert sr == SR
    return data


def _synthesize(path: Path, pause_sec: float) -> None:
    chunk = _real_speech_chunk()
    silence = lambda sec: np.zeros(int(SR * sec), dtype=np.float32)
    signal = np.concatenate([
        silence(0.3), chunk, silence(pause_sec), chunk, silence(0.3),
    ])
    sf.write(path, signal, SR)


def _take_from_file(path: Path) -> dict:
    segments = detect_speech_segments(str(path))
    features = compute_timing_features(segments, passage_syllable_count=10)
    return {
        "pause_fraction": features.pause_fraction,
        "longest_internal_gap": features.longest_internal_gap,
        "speaking_rate": features.speaking_rate,
    }


def test_full_pipeline_triggers_and_resolves_via_answer(tmp_path):
    reference_takes = []
    for i in range(4):
        path = tmp_path / f"ref_{i}.wav"
        _synthesize(path, pause_sec=0.4 + 0.02 * i)
        reference_takes.append(_take_from_file(path))
    baseline = fit_baseline(reference_takes)

    tracker = PersistentDeviationTracker(threshold=2.0, required_consecutive=2)

    deviant_path = tmp_path / "deviant.wav"
    _synthesize(deviant_path, pause_sec=4.0)

    first = evaluate_checkin(str(deviant_path), baseline, tracker, "copd", passage_syllable_count=10)
    assert first.triggered is False  # one hit isn't persistent yet

    second = evaluate_checkin(str(deviant_path), baseline, tracker, "copd", passage_syllable_count=10)
    assert second.triggered is True
    assert second.question_text == "What happened during that pause?"

    # A follow-up question means the conversation isn't finished -- the
    # note correctly stays unresolved until that follow-up is answered too.
    note, follow_up = process_answer("copd", second.deviation_score, "I stopped to catch my breath")
    assert follow_up == "Is that more frequent than usual, and what were you doing at the time?"
    assert note.patient_said == "I stopped to catch my breath"
    assert note.unresolved != []

    # No further card exists for this cue either way, but an answer that
    # doesn't match any known keyword is honestly unclassified, not
    # resolved -- this deterministic matcher has no real understanding of
    # "mainly on stairs" as an answer; claiming otherwise would be the
    # exact bug (conflating "nothing left to ask" with "we understood
    # this") that this fix exists to catch. The upcoming RAG-based
    # selector is what actually closes this gap with real comprehension.
    final_note, final_follow_up = process_answer("copd", second.deviation_score, "most days now, mainly on stairs")
    assert final_follow_up is None
    assert final_note.unresolved != []


def test_pipeline_does_not_trigger_on_typical_take(tmp_path):
    reference_takes = []
    for i in range(4):
        path = tmp_path / f"ref_{i}.wav"
        _synthesize(path, pause_sec=0.4 + 0.02 * i)
        reference_takes.append(_take_from_file(path))
    baseline = fit_baseline(reference_takes)
    tracker = PersistentDeviationTracker(threshold=2.0, required_consecutive=2)

    typical_path = tmp_path / "typical.wav"
    _synthesize(typical_path, pause_sec=0.42)

    result = evaluate_checkin(str(typical_path), baseline, tracker, "copd", passage_syllable_count=10)
    assert result.triggered is False
    assert result.question_text is None
