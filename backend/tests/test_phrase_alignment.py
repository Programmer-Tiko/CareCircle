"""Tests for phrase_alignment: comparable-phrase verification and pause localization.

Test categories (from ANTIGRAVITY-TASK.md & ANTIGRAVITY-REVIEW-FIXES.md):
 - Exact passage match
 - Punctuation/case normalization (including Unicode smart quotes & dashes)
 - Position-aware pause localization (including reproducer cases)
 - Repeated/missing words
 - Wrong passage entirely
 - Low-confidence and corrupt/NaN transcripts
 - Nonmonotonic and invalid timestamps
 - Caller error handling (empty expected text, invalid thresholds)
 - Smoke run with real local ASR (cached-only, gated behind CADENCE_ASR_SMOKE=1)

All tests except the smoke test use injectable fake transcribers —
no model downloads, no audio files, fully deterministic.
"""
import math
import os
import pytest

from app.audio.phrase_alignment import (
    LOW_CONFIDENCE_THRESHOLD,
    MATCH_WER_THRESHOLD,
    MISMATCH_WER_THRESHOLD,
    PauseEvent,
    PhraseMatchResult,
    TranscriptionResult,
    WordTimestamp,
    _levenshtein_ops,
    localize_pauses,
    normalize_token,
    normalize_tokens,
    verify_phrase,
)
from app.passage import PASSAGE_TEXT


# ---------------------------------------------------------------------------
# Helper: build a fake transcriber from a list of WordTimestamps
# ---------------------------------------------------------------------------

def _make_transcriber(
    words: list[WordTimestamp],
    overall_confidence: float = 0.95,
    model_id: str = "injected-test-stub",
):
    """Return a callable(wav_path) -> TranscriptionResult with fixed output."""
    def _transcribe(wav_path: str) -> TranscriptionResult:
        return TranscriptionResult(
            words=words,
            overall_confidence=overall_confidence,
            model_id=model_id,
        )
    return _transcribe


def _words_from_text(
    text: str,
    *,
    gap: float = 0.05,
    word_dur: float = 0.3,
    confidence: float = 0.95,
    start_time: float = 0.0,
    pauses: dict[int, float] | None = None,
) -> list[WordTimestamp]:
    """Generate synthetic word timestamps from text."""
    pauses = pauses or {}
    tokens = text.split()
    words: list[WordTimestamp] = []
    t = start_time

    for i, token in enumerate(tokens):
        if i > 0:
            t += pauses.get(i, gap)
        words.append(WordTimestamp(
            word=token,
            start=round(t, 4),
            end=round(t + word_dur, 4),
            confidence=confidence,
        ))
        t += word_dur

    return words


# ===== Normalization tests =====

class TestNormalization:
    def test_lowercase(self):
        assert normalize_token("When") == "when"

    def test_strip_punctuation(self):
        assert normalize_token("rainbow.") == "rainbow"
        assert normalize_token("'air,'") == "air"

    def test_preserve_internal_apostrophe(self):
        assert normalize_token("don't") == "don't"

    def test_empty(self):
        assert normalize_token("") == ""
        assert normalize_token("...") == ""

    def test_normalize_tokens_passage(self):
        tokens = normalize_tokens(PASSAGE_TEXT)
        assert len(tokens) == 29  # Rainbow passage first two sentences
        assert tokens[0] == "when"
        assert tokens[-1] == "colors"

    def test_unicode_quotes_and_dashes_normalized(self):
        assert normalize_token("don\u2019t") == "don't"
        assert normalize_token("\u2018word\u2019") == "word"
        assert normalize_token("word\u2014another") == "wordanother"  # dash stripped as punct


# ===== Levenshtein edit distance =====

class TestLevenshtein:
    def test_identical(self):
        tokens = ["when", "the", "sunlight"]
        assert _levenshtein_ops(tokens, tokens) == (0, 0, 0)

    def test_substitution(self):
        expected = ["when", "the", "sunlight"]
        observed = ["when", "a", "sunlight"]
        subs, ins, dels = _levenshtein_ops(expected, observed)
        assert subs == 1 and ins == 0 and dels == 0

    def test_insertion(self):
        expected = ["when", "sunlight"]
        observed = ["when", "the", "sunlight"]
        subs, ins, dels = _levenshtein_ops(expected, observed)
        assert ins == 1 and subs == 0 and dels == 0

    def test_deletion(self):
        expected = ["when", "the", "sunlight"]
        observed = ["when", "sunlight"]
        subs, ins, dels = _levenshtein_ops(expected, observed)
        assert dels == 1 and subs == 0 and ins == 0

    def test_empty_observed(self):
        expected = ["a", "b", "c"]
        subs, ins, dels = _levenshtein_ops(expected, [])
        assert dels == 3 and subs == 0 and ins == 0

    def test_empty_expected(self):
        subs, ins, dels = _levenshtein_ops([], ["a", "b"])
        assert ins == 2 and subs == 0 and dels == 0


# ===== Pause localization =====

class TestPauseLocalization:
    def test_no_pauses_below_threshold(self):
        words = _words_from_text("when the sunlight", gap=0.05)
        events = localize_pauses(words, PASSAGE_TEXT, pause_threshold=0.15)
        assert len(events) == 0

    def test_detects_pause_above_threshold(self):
        words = _words_from_text(
            "when the sunlight",
            gap=0.05,
            pauses={2: 0.5},
        )
        events = localize_pauses(words, PASSAGE_TEXT, pause_threshold=0.15)
        assert len(events) == 1
        assert events[0].before_word == "the"
        assert events[0].after_word == "sunlight"
        assert events[0].duration == pytest.approx(0.5, abs=0.01)
        assert events[0].provenance == "measured"

    def test_punctuation_adjacent_classification_at_boundary(self):
        text = "in the air, they act"
        words = _words_from_text(text, gap=0.05, pauses={3: 0.4})
        events = localize_pauses(words, PASSAGE_TEXT, pause_threshold=0.15)
        assert len(events) == 1
        assert events[0].category == "punctuation_adjacent"

    def test_within_clause_classification(self):
        text = "the sunlight strikes"
        words = _words_from_text(text, gap=0.05, pauses={2: 0.4})
        events = localize_pauses(words, PASSAGE_TEXT, pause_threshold=0.15)
        assert len(events) == 1
        assert events[0].category == "within_clause"

    def test_nonmonotonic_timestamps(self):
        words = [
            WordTimestamp("when", 0.0, 0.3, 0.9),
            WordTimestamp("the", 0.2, 0.5, 0.9),  # starts before prev ends
            WordTimestamp("sunlight", 0.6, 0.9, 0.9),
        ]
        events = localize_pauses(words, PASSAGE_TEXT, pause_threshold=0.15)
        nonmono = [e for e in events if e.provenance == "nonmonotonic_boundary"]
        assert len(nonmono) == 1
        assert nonmono[0].duration == 0.0
        assert nonmono[0].before_word == "when"
        assert nonmono[0].after_word == "the"

    def test_invalid_nan_timestamps_not_measured_zero(self):
        words = [
            WordTimestamp("when", float("nan"), 0.3, 0.9),
            WordTimestamp("the", 0.4, 0.8, 0.9),
        ]
        events = localize_pauses(words, PASSAGE_TEXT, pause_threshold=0.15)
        assert len(events) == 1
        assert events[0].provenance == "invalid_timestamp"
        assert events[0].duration == 0.0

    def test_single_word_no_pauses(self):
        words = [WordTimestamp("when", 0.0, 0.3, 0.9)]
        assert localize_pauses(words, PASSAGE_TEXT) == []

    def test_empty_words(self):
        assert localize_pauses([], PASSAGE_TEXT) == []


# ===== verify_phrase: exact match =====

class TestExactPassageMatch:
    def test_exact_passage_matched(self):
        words = _words_from_text(PASSAGE_TEXT)
        transcriber = _make_transcriber(words)
        result = verify_phrase("dummy.wav", transcriber)

        assert result.phrase_match == "matched"
        assert result.mismatch_score == 0.0
        assert result.substitutions == 0
        assert result.insertions == 0
        assert result.deletions == 0
        assert result.alignment_available is True
        assert result.model_id == "injected-test-stub"

    def test_exact_tokens_match_passage(self):
        words = _words_from_text(PASSAGE_TEXT)
        transcriber = _make_transcriber(words)
        result = verify_phrase("dummy.wav", transcriber)

        assert result.expected_tokens == normalize_tokens(PASSAGE_TEXT)
        assert result.observed_tokens == normalize_tokens(PASSAGE_TEXT)


# ===== verify_phrase: normalization invariance =====

class TestNormalizationInvariance:
    def test_case_insensitive_match(self):
        words = _words_from_text(PASSAGE_TEXT.upper())
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        assert result.phrase_match == "matched"
        assert result.mismatch_score == 0.0

    def test_punctuation_stripped_match(self):
        stripped = PASSAGE_TEXT.replace(",", "").replace(".", "")
        words = _words_from_text(stripped)
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        assert result.phrase_match == "matched"
        assert result.mismatch_score == 0.0

    def test_extra_punctuation_match(self):
        extra = PASSAGE_TEXT.replace("rainbow", "rainbow,").replace("colors", "colors!")
        words = _words_from_text(extra)
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        assert result.phrase_match == "matched"
        assert result.mismatch_score == 0.0

    def test_unicode_punctuation_match(self):
        curly = PASSAGE_TEXT.replace("air,", "air\u2014").replace("colors.", "colors\u2026")
        words = _words_from_text(curly)
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        assert result.phrase_match == "matched"
        assert result.mismatch_score == 0.0


# ===== verify_phrase: repeated/missing words =====

class TestRepeatedMissingWords:
    def test_repeated_word(self):
        passage_words = PASSAGE_TEXT.split()
        idx = passage_words.index("the")
        modified = passage_words[:idx + 1] + ["the"] + passage_words[idx + 1:]
        text = " ".join(modified)
        words = _words_from_text(text)
        result = verify_phrase("dummy.wav", _make_transcriber(words))

        assert result.insertions >= 1
        assert result.mismatch_score > 0
        assert result.phrase_match == "matched"

    def test_missing_word(self):
        passage_words = PASSAGE_TEXT.split()
        modified = [w for w in passage_words if w.lower() != "beautiful"]
        text = " ".join(modified)
        words = _words_from_text(text)
        result = verify_phrase("dummy.wav", _make_transcriber(words))

        assert result.deletions >= 1
        assert result.mismatch_score > 0
        assert result.phrase_match == "matched"

    def test_multiple_missing_words_uncertain(self):
        passage_words = PASSAGE_TEXT.split()
        modified = passage_words[:5] + passage_words[11:]
        text = " ".join(modified)
        words = _words_from_text(text)
        result = verify_phrase("dummy.wav", _make_transcriber(words))

        assert result.deletions >= 4
        assert result.mismatch_score > MATCH_WER_THRESHOLD
        assert result.phrase_match in ("uncertain", "mismatch")


# ===== verify_phrase: wrong passage =====

class TestWrongPassage:
    def test_completely_different_passage(self):
        wrong_text = (
            "The quick brown fox jumps over the lazy dog. "
            "Pack my box with five dozen liquor jugs."
        )
        words = _words_from_text(wrong_text)
        result = verify_phrase("dummy.wav", _make_transcriber(words))

        assert result.phrase_match == "mismatch"
        assert result.mismatch_score >= MISMATCH_WER_THRESHOLD

    def test_partially_correct_uncertain(self):
        passage_words = PASSAGE_TEXT.split()
        half = len(passage_words) // 2
        mixed = passage_words[:half] + ["something", "completely", "different"] * 3
        text = " ".join(mixed)
        words = _words_from_text(text)
        result = verify_phrase("dummy.wav", _make_transcriber(words))

        assert result.phrase_match in ("uncertain", "mismatch")
        assert result.mismatch_score > MATCH_WER_THRESHOLD


# ===== verify_phrase: low confidence and corrupted data =====

class TestLowConfidenceAndCorruption:
    def test_low_overall_confidence_uncertain(self):
        words = _words_from_text(PASSAGE_TEXT)
        transcriber = _make_transcriber(
            words, overall_confidence=0.1, model_id="noisy-stub"
        )
        result = verify_phrase("dummy.wav", transcriber)

        assert result.phrase_match == "uncertain"
        assert "confidence" in result.phrase_match_reason.lower()
        assert any("confidence" in lim.lower() for lim in result.limitations)

    def test_low_per_word_confidence_noted(self):
        words = _words_from_text(PASSAGE_TEXT, confidence=0.1)
        transcriber = _make_transcriber(words, overall_confidence=0.9)
        result = verify_phrase("dummy.wav", transcriber)

        assert any("words have confidence" in lim for lim in result.limitations)

    def test_zero_confidence_empty_recording(self):
        transcriber = _make_transcriber(
            [], overall_confidence=0.0, model_id="empty-stub"
        )
        result = verify_phrase("dummy.wav", transcriber)

        assert result.phrase_match == "uncertain"
        assert result.alignment_available is False
        assert result.mismatch_score == 1.0
        assert len(result.pause_events) == 0

    def test_reproducer_corrupt_nan_timestamp_and_confidence(self):
        """Reproducer from ANTIGRAVITY-REVIEW-FIXES.md:
        WordTimestamp('hello', NaN, -1, NaN) with overall_confidence=NaN
        previously returned matched and alignment_available=True.
        MUST NOW return phrase_match='uncertain' and alignment_available=False!
        """
        words = [WordTimestamp("hello", float("nan"), -1.0, float("nan"))]
        transcriber = _make_transcriber(words, overall_confidence=float("nan"))

        result = verify_phrase(
            "dummy.wav",
            transcriber,
            expected_passage="hello",
        )
        assert result.phrase_match == "uncertain", (
            f"Corrupt NaN confidence must yield uncertain, got {result.phrase_match}"
        )
        assert result.alignment_available is False, (
            "Corrupt NaN/-1 timestamps must yield alignment_available=False"
        )
        assert any("not in [0.0, 1.0]" in lim or "not finite" in lim for lim in result.limitations)


# ===== verify_phrase: caller error validation =====

class TestCallerErrorValidation:
    def test_empty_expected_passage_raises_value_error(self):
        words = _words_from_text("hello world")
        transcriber = _make_transcriber(words)
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            verify_phrase("dummy.wav", transcriber, expected_passage="")

    def test_invalid_thresholds_raise_value_error(self):
        words = _words_from_text("hello world")
        transcriber = _make_transcriber(words)
        with pytest.raises(ValueError, match="strictly less than"):
            verify_phrase("dummy.wav", transcriber, expected_passage="hello world", match_threshold=0.6, mismatch_threshold=0.5)

        with pytest.raises(ValueError, match="must be finite"):
            verify_phrase("dummy.wav", transcriber, expected_passage="hello world", match_threshold=float("nan"))


# ===== verify_phrase: nonmonotonic timestamps =====

class TestNonmonotonicTimestamps:
    def test_nonmonotonic_recorded_in_limitations(self):
        words = [
            WordTimestamp("when", 0.0, 0.3, 0.9),
            WordTimestamp("the", 0.2, 0.5, 0.9),  # nonmonotonic
            WordTimestamp("sunlight", 0.6, 1.0, 0.9),
            WordTimestamp("strikes", 1.1, 1.5, 0.9),
            WordTimestamp("raindrops", 1.6, 2.0, 0.9),
            WordTimestamp("in", 2.1, 2.3, 0.9),
            WordTimestamp("the", 2.4, 2.6, 0.9),
            WordTimestamp("air", 2.7, 3.0, 0.9),
            WordTimestamp("they", 3.1, 3.3, 0.9),
            WordTimestamp("act", 3.4, 3.6, 0.9),
            WordTimestamp("as", 3.7, 3.9, 0.9),
            WordTimestamp("a", 4.0, 4.1, 0.9),
            WordTimestamp("prism", 4.2, 4.5, 0.9),
            WordTimestamp("and", 4.6, 4.8, 0.9),
            WordTimestamp("form", 4.9, 5.1, 0.9),
            WordTimestamp("a", 5.2, 5.3, 0.9),
            WordTimestamp("rainbow", 5.4, 5.8, 0.9),
            WordTimestamp("The", 5.9, 6.1, 0.9),
            WordTimestamp("rainbow", 6.2, 6.5, 0.9),
            WordTimestamp("is", 6.6, 6.8, 0.9),
            WordTimestamp("a", 6.9, 7.0, 0.9),
            WordTimestamp("division", 7.1, 7.5, 0.9),
            WordTimestamp("of", 7.6, 7.7, 0.9),
            WordTimestamp("white", 7.8, 8.0, 0.9),
            WordTimestamp("light", 8.1, 8.3, 0.9),
            WordTimestamp("into", 8.4, 8.6, 0.9),
            WordTimestamp("many", 8.7, 8.9, 0.9),
            WordTimestamp("beautiful", 9.0, 9.4, 0.9),
            WordTimestamp("colors", 9.5, 9.8, 0.9),
        ]
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        assert any("nonmonotonic" in lim.lower() for lim in result.limitations)
        nonmono = [e for e in result.pause_events if e.provenance == "nonmonotonic_boundary"]
        assert len(nonmono) >= 1


# ===== verify_phrase: pause classification at punctuation vs within clause =====

class TestPauseClassificationInContext:
    def test_pause_after_air_comma_is_punctuation_adjacent(self):
        # 0.6s pause after "air," (between "air" and "they")
        words = _words_from_text(
            PASSAGE_TEXT,
            gap=0.05,
            pauses={8: 0.6},  # word index 8 is "they" in passage words
        )
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        air_pauses = [
            e for e in result.pause_events
            if e.before_word.lower().startswith("air")
        ]
        assert len(air_pauses) >= 1
        assert air_pauses[0].category == "punctuation_adjacent"

    def test_pause_before_air_is_within_clause(self):
        # 0.6s pause before "air," (between "the" and "air,")
        words = _words_from_text(
            PASSAGE_TEXT,
            gap=0.05,
            pauses={7: 0.6},  # word index 7 is "air"
        )
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        before_air_pauses = [
            e for e in result.pause_events
            if e.after_word.lower().startswith("air")
        ]
        assert len(before_air_pauses) >= 1
        assert before_air_pauses[0].category == "within_clause"

    def test_pause_within_clause(self):
        words = _words_from_text(
            PASSAGE_TEXT,
            gap=0.05,
            pauses={2: 0.5},
        )
        result = verify_phrase("dummy.wav", _make_transcriber(words))
        sun_pauses = [
            e for e in result.pause_events
            if "sunlight" in e.after_word.lower()
        ]
        assert len(sun_pauses) >= 1
        assert sun_pauses[0].category == "within_clause"


# ===== verify_phrase: alignment_available flag =====

class TestAlignmentAvailable:
    def test_available_when_words_present(self):
        words = _words_from_text("when the sunlight")
        result = verify_phrase(
            "dummy.wav", _make_transcriber(words),
            expected_passage="when the sunlight",
        )
        assert result.alignment_available is True
        assert len(result.word_timestamps) == 3

    def test_unavailable_when_empty(self):
        result = verify_phrase(
            "dummy.wav",
            _make_transcriber([], overall_confidence=0.0),
        )
        assert result.alignment_available is False
        assert len(result.word_timestamps) == 0


# ===== Edge cases =====

class TestEdgeCases:
    def test_single_word_expected_and_observed(self):
        words = [WordTimestamp("hello", 0.0, 0.3, 0.9)]
        result = verify_phrase(
            "dummy.wav", _make_transcriber(words),
            expected_passage="hello",
        )
        assert result.phrase_match == "matched"
        assert result.mismatch_score == 0.0

    def test_wer_capped_at_one(self):
        observed = " ".join(["word"] * 30)
        words = _words_from_text(observed)
        result = verify_phrase(
            "dummy.wav", _make_transcriber(words),
            expected_passage="a b c",
        )
        assert result.mismatch_score <= 1.0

    def test_result_dataclass_fields(self):
        words = _words_from_text(PASSAGE_TEXT)
        result = verify_phrase("dummy.wav", _make_transcriber(words))

        assert hasattr(result, "expected_tokens")
        assert hasattr(result, "observed_tokens")
        assert hasattr(result, "substitutions")
        assert hasattr(result, "insertions")
        assert hasattr(result, "deletions")
        assert hasattr(result, "mismatch_score")
        assert hasattr(result, "phrase_match")
        assert hasattr(result, "phrase_match_reason")
        assert hasattr(result, "pause_events")
        assert hasattr(result, "alignment_available")
        assert hasattr(result, "word_timestamps")
        assert hasattr(result, "model_id")
        assert hasattr(result, "overall_confidence")
        assert hasattr(result, "limitations")


# ===== Adversarial and Cross-Module Integration Tests =====

class TestAdversarialCrossModuleIntegration:
    def test_mixed_valid_and_corrupt_timestamps(self):
        """A transcript where word 2 has NaN start time:
        - Transcript text is usable (3 words)
        - Alignment availability must be False
        - Pause events must flag invalid_timestamp
        - Phrase match should still evaluate text match
        """
        words = [
            WordTimestamp("when", 0.0, 0.3, 0.9),
            WordTimestamp("the", float("nan"), 0.6, 0.9),  # corrupt
            WordTimestamp("sunlight", 0.7, 1.0, 0.9),
        ]
        res = verify_phrase("dummy.wav", _make_transcriber(words), expected_passage="when the sunlight")
        assert res.alignment_available is False
        assert any("start is not finite" in lim for lim in res.limitations)
        # Invalid timestamp boundary is flagged
        assert any(e.provenance == "invalid_timestamp" for e in res.pause_events)

    def test_out_of_range_word_confidences_flagged(self):
        """Words with confidence > 1.0 or < 0.0 must be flagged in limitations."""
        words = [
            WordTimestamp("when", 0.0, 0.3, 1.5),
            WordTimestamp("the", 0.4, 0.6, -0.5),
        ]
        res = verify_phrase("dummy.wav", _make_transcriber(words), expected_passage="when the")
        assert any("confidence is not in [0.0, 1.0]" in lim for lim in res.limitations)

    def test_unicode_smart_quotes_and_em_dashes_in_expected_and_observed(self):
        """Expected text with curly quotes and em-dash matches observed plain or Unicode."""
        expected = "“When the sunlight strikes—it shines.”"
        observed = "When the sunlight strikes-it shines."
        words = _words_from_text(observed)
        res = verify_phrase("dummy.wav", _make_transcriber(words), expected_passage=expected)
        assert res.phrase_match == "matched"
        assert res.mismatch_score == 0.0

    def test_uncapped_wer_simulation_is_bounded_at_one(self):
        """3 expected words, 50 inserted words would have standard WER > 15.0.
        Our mismatch_score must be strictly bounded at 1.0.
        """
        words = _words_from_text(" ".join(["extra"] * 50))
        res = verify_phrase("dummy.wav", _make_transcriber(words), expected_passage="a b c")
        assert res.mismatch_score == 1.0
        assert res.phrase_match == "mismatch"


# ===== Smoke test with real ASR (opt-in only) =====

class TestRealASRSmoke:
    """Smoke test using a real local ASR model.

    Gated behind CADENCE_ASR_SMOKE=1 environment variable.
    """

    @pytest.mark.skipif(
        os.environ.get("CADENCE_ASR_SMOKE") != "1",
        reason="Real ASR smoke requires CADENCE_ASR_SMOKE=1 environment variable",
    )
    def test_real_asr_smoke(self):
        try:
            from app.audio.whisper_adapter import CachedWhisperTranscriber
            transcriber = CachedWhisperTranscriber(model_size="base")
        except (ImportError, FileNotFoundError) as exc:
            pytest.skip(f"Whisper not ready for smoke test: {exc}")

        test_audio_path = "/tmp/live_test_audio/pd_real_chunk_a.wav"
        if not os.path.exists(test_audio_path):
            pytest.skip(f"No audio file at {test_audio_path}")

        result = verify_phrase(test_audio_path, transcriber)
        assert result.phrase_match in ("matched", "mismatch", "uncertain")
        assert 0.0 <= result.mismatch_score <= 1.0
        assert isinstance(result.pause_events, list)
        assert result.model_id == "whisper-base"
        print(f"\nReal ASR smoke: match={result.phrase_match}, "
              f"WER={result.mismatch_score:.3f}, "
              f"words={len(result.word_timestamps)}")


def test_empty_asr_tokens_do_not_shift_expected_pause_position():
    words = [WordTimestamp('in',0,.1,.95),WordTimestamp('',.11,.12,.95),
             WordTimestamp('the',.2,.3,.95),WordTimestamp('air',.4,.5,.95),
             WordTimestamp('they',1.,1.1,.95),WordTimestamp('act',1.2,1.3,.95)]
    result = verify_phrase('unused',lambda _:TranscriptionResult(words,.95,'stub'),
                           expected_passage='in the air, they act')
    assert result.alignment_available
    assert len(result.word_timestamps) == 5
    event = result.pause_events[0]
    assert event.category == 'punctuation_adjacent'
    assert result.word_timestamps[event.position].word == 'they'


def test_standalone_expected_punctuation_does_not_shift_indices():
    words = [WordTimestamp('hello',0,.2,.95),WordTimestamp('world',.7,.9,.95),
             WordTimestamp('again',1.4,1.6,.95)]
    result = verify_phrase('unused',lambda _:TranscriptionResult(words,.95,'stub'),
                           expected_passage='hello ... world again')
    assert [event.category for event in result.pause_events] == ['punctuation_adjacent','within_clause']


def test_global_timestamp_order_disables_alignment():
    words = [WordTimestamp('hello',1,1.5,.95),WordTimestamp('world',.5,.8,.95)]
    result = verify_phrase('unused',lambda _:TranscriptionResult(words,.95,'stub'),
                           expected_passage='hello world')
    assert result.phrase_match == 'matched'  # text can match while timing is unusable
    assert result.alignment_available is False
    assert any('overlap or run backwards' in note for note in result.limitations)
