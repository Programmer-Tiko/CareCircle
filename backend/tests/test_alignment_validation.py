"""Tests for alignment and transcription evidence validation."""
import math
import pytest

from app.audio.alignment_validation import (
    TimestampValidity,
    TranscriptionValidity,
    normalize_unicode,
    validate_expected_passage,
    validate_thresholds,
    validate_transcription,
    validate_word_timestamp,
)
from app.audio.phrase_alignment import TranscriptionResult, WordTimestamp


class TestValidateWordTimestamp:
    def test_valid_word_timestamp(self):
        wt = WordTimestamp("hello", 0.0, 0.5, 0.95)
        v = validate_word_timestamp(wt)
        assert v.text_usable is True
        assert v.timestamps_usable is True
        assert v.confidence_usable is True
        assert len(v.issues) == 0

    def test_nan_start_invalid(self):
        wt = WordTimestamp("hello", float("nan"), 0.5, 0.95)
        v = validate_word_timestamp(wt)
        assert v.text_usable is True
        assert v.timestamps_usable is False
        assert any("start is not finite" in iss for iss in v.issues)

    def test_nan_end_invalid(self):
        wt = WordTimestamp("hello", 0.0, float("nan"), 0.95)
        v = validate_word_timestamp(wt)
        assert v.timestamps_usable is False

    def test_infinite_timestamps_invalid(self):
        wt = WordTimestamp("hello", 0.0, float("inf"), 0.95)
        v = validate_word_timestamp(wt)
        assert v.timestamps_usable is False

    def test_negative_start_or_end_invalid(self):
        wt = WordTimestamp("hello", -0.1, 0.5, 0.95)
        v = validate_word_timestamp(wt)
        assert v.timestamps_usable is False
        assert any("start is negative" in iss for iss in v.issues)

        wt2 = WordTimestamp("hello", 0.0, -0.5, 0.95)
        v2 = validate_word_timestamp(wt2)
        assert v2.timestamps_usable is False

    def test_start_greater_than_end_invalid(self):
        wt = WordTimestamp("hello", 1.5, 1.0, 0.95)
        v = validate_word_timestamp(wt)
        assert v.timestamps_usable is False
        assert any("start (1.5) > end (1.0)" in iss for iss in v.issues)

    def test_nan_confidence_invalid(self):
        wt = WordTimestamp("hello", 0.0, 0.5, float("nan"))
        v = validate_word_timestamp(wt)
        assert v.confidence_usable is False
        assert any("confidence is not in [0.0, 1.0]" in iss for iss in v.issues)

    def test_out_of_range_confidence_invalid(self):
        wt1 = WordTimestamp("hello", 0.0, 0.5, 1.5)
        assert validate_word_timestamp(wt1).confidence_usable is False

        wt2 = WordTimestamp("hello", 0.0, 0.5, -0.1)
        assert validate_word_timestamp(wt2).confidence_usable is False

    def test_empty_or_whitespace_word_invalid(self):
        assert validate_word_timestamp(WordTimestamp("", 0.0, 0.5, 0.9)).text_usable is False
        assert validate_word_timestamp(WordTimestamp("   ", 0.0, 0.5, 0.9)).text_usable is False

    def test_reproducer_corrupt_word_timestamp(self):
        """WordTimestamp('hello', NaN, -1, NaN) must have timestamps_usable=False
        and confidence_usable=False."""
        wt = WordTimestamp("hello", float("nan"), -1.0, float("nan"))
        v = validate_word_timestamp(wt)
        assert v.text_usable is True
        assert v.timestamps_usable is False
        assert v.confidence_usable is False


class TestValidateTranscription:
    def test_valid_transcription(self):
        words = [WordTimestamp("hello", 0.0, 0.3, 0.9), WordTimestamp("world", 0.4, 0.8, 0.85)]
        tr = TranscriptionResult(words=words, overall_confidence=0.88, model_id="test")
        v = validate_transcription(tr)
        assert v.transcript_usable is True
        assert v.alignment_usable is True
        assert v.confidence_usable is True
        assert v.usable_word_count == 2

    def test_nan_overall_confidence_invalid(self):
        words = [WordTimestamp("hello", 0.0, 0.3, 0.9)]
        tr = TranscriptionResult(words=words, overall_confidence=float("nan"), model_id="test")
        v = validate_transcription(tr)
        assert v.confidence_usable is False
        assert any("overall_confidence is not in" in iss for iss in v.issues)

    def test_reproducer_corrupt_transcription_rejected(self):
        """Reproducer from ANTIGRAVITY-REVIEW-FIXES.md:
        WordTimestamp('hello', NaN, -1, NaN) with overall_confidence=NaN.
        """
        words = [WordTimestamp("hello", float("nan"), -1.0, float("nan"))]
        tr = TranscriptionResult(words=words, overall_confidence=float("nan"), model_id="test")
        v = validate_transcription(tr)
        assert v.transcript_usable is True
        assert v.alignment_usable is False  # Alignment is NOT usable!
        assert v.confidence_usable is False

    def test_all_zero_per_word_confidence_flagged(self):
        words = [WordTimestamp("hello", 0.0, 0.3, 0.0), WordTimestamp("world", 0.4, 0.8, 0.0)]
        tr = TranscriptionResult(words=words, overall_confidence=0.8, model_id="test")
        v = validate_transcription(tr)
        assert any("all word confidences zero" in iss for iss in v.issues)

    def test_empty_transcription(self):
        tr = TranscriptionResult(words=[], overall_confidence=0.0, model_id="test")
        v = validate_transcription(tr)
        assert v.transcript_usable is False
        assert v.alignment_usable is False


class TestValidateThresholds:
    def test_valid_thresholds_pass(self):
        validate_thresholds(
            match_threshold=0.15,
            mismatch_threshold=0.50,
            confidence_threshold=0.30,
            pause_threshold=0.15,
        )

    def test_nan_threshold_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            validate_thresholds(float("nan"), 0.5, 0.3, 0.15)

    def test_match_gte_mismatch_raises(self):
        with pytest.raises(ValueError, match="strictly less than"):
            validate_thresholds(0.5, 0.5, 0.3, 0.15)
        with pytest.raises(ValueError, match="strictly less than"):
            validate_thresholds(0.6, 0.5, 0.3, 0.15)

    def test_out_of_range_thresholds_raise(self):
        with pytest.raises(ValueError, match="match_threshold must be in"):
            validate_thresholds(-0.1, 0.5, 0.3, 0.15)
        with pytest.raises(ValueError, match="pause_threshold must be >= 0"):
            validate_thresholds(0.15, 0.5, 0.3, -0.01)


class TestValidateExpectedPassage:
    def test_valid_passage(self):
        validate_expected_passage("When the sunlight strikes")

    def test_empty_or_whitespace_passage_raises(self):
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            validate_expected_passage("")
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            validate_expected_passage("   \n\t  ")

    def test_none_passage_raises(self):
        with pytest.raises(ValueError):
            validate_expected_passage(None)


class TestUnicodeNormalization:
    def test_curly_apostrophes(self):
        # \u2018 and \u2019 -> '
        text = "don\u2019t wouldn\u2018t"
        assert normalize_unicode(text) == "don't wouldn't"

    def test_curly_double_quotes(self):
        text = "\u201chello\u201d"
        assert normalize_unicode(text) == '"hello"'

    def test_em_and_en_dashes(self):
        text = "word\u2014another\u2013word"
        assert normalize_unicode(text) == "word-another-word"

    def test_ellipsis(self):
        text = "waiting\u2026"
        assert normalize_unicode(text) == "waiting..."
