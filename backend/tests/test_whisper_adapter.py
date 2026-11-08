"""Tests for CachedWhisperTranscriber adapter."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.audio.whisper_adapter import CachedWhisperTranscriber, _DEFAULT_CACHE_DIR


class TestCachedWhisperTranscriberUnit:
    def test_find_cached_model_returns_none_if_missing(self, tmp_path, monkeypatch):
        fake_cache = tmp_path / "whisper"
        fake_cache.mkdir()
        monkeypatch.setattr("app.audio.whisper_adapter._DEFAULT_CACHE_DIR", fake_cache)

        assert CachedWhisperTranscriber.find_cached_model("nonexistent") is None

    def test_find_cached_model_returns_path_if_present(self, tmp_path, monkeypatch):
        fake_cache = tmp_path / "whisper"
        fake_cache.mkdir()
        model_file = fake_cache / "base.pt"
        model_file.write_text("fake-weights")
        monkeypatch.setattr("app.audio.whisper_adapter._DEFAULT_CACHE_DIR", fake_cache)

        found = CachedWhisperTranscriber.find_cached_model("base")
        assert found == str(model_file)

    def test_raises_import_error_when_whisper_not_installed(self, monkeypatch):
        # Force whisper import to fail
        with patch.dict(sys.modules, {"whisper": None}):
            with pytest.raises(ImportError, match="openai-whisper is not installed"):
                CachedWhisperTranscriber(model_size="base")

    def test_raises_file_not_found_when_model_not_cached(self, monkeypatch):
        # Pretend whisper is importable, but find_cached_model returns None
        mock_whisper = MagicMock()
        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            monkeypatch.setattr(
                CachedWhisperTranscriber, "find_cached_model", staticmethod(lambda m: None)
            )
            with pytest.raises(FileNotFoundError, match="model weights not found"):
                CachedWhisperTranscriber(model_size="base")

    def test_loads_model_once_and_reuses_across_calls(self, monkeypatch):
        # Prove model is loaded once at init, and transcribe called per invoke
        mock_whisper = MagicMock()
        mock_model = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "words": [
                        {"word": "hello", "start": 0.0, "end": 0.5, "probability": 0.9},
                        {"word": "world", "start": 0.6, "end": 1.0, "probability": 0.85},
                    ],
                    "no_speech_prob": 0.05,
                }
            ]
        }

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            monkeypatch.setattr(
                CachedWhisperTranscriber, "find_cached_model", staticmethod(lambda m: "/path/base.pt")
            )

            transcriber = CachedWhisperTranscriber(model_size="base")
            assert mock_whisper.load_model.call_count == 1

            # Call first time
            res1 = transcriber("audio1.wav")
            assert mock_model.transcribe.call_count == 1
            assert len(res1.words) == 2
            assert res1.words[0].word == "hello"

            # Call second time — load_model MUST NOT be called again
            res2 = transcriber("audio2.wav")
            assert mock_whisper.load_model.call_count == 1
            assert mock_model.transcribe.call_count == 2

    def test_download_root_directed_to_cache_dir_no_implicit_download(self, monkeypatch):
        mock_whisper = MagicMock()
        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            monkeypatch.setattr(
                CachedWhisperTranscriber, "find_cached_model", staticmethod(lambda m: "/path/base.pt")
            )
            CachedWhisperTranscriber(model_size="base")

            # Check kwargs sent to load_model
            _, kwargs = mock_whisper.load_model.call_args
            assert kwargs.get("download_root") == str(_DEFAULT_CACHE_DIR)


class TestRealASRSmokeOptIn:
    """Real ASR smoke test explicitly gated behind CADENCE_ASR_SMOKE=1."""

    @pytest.mark.skipif(
        os.environ.get("CADENCE_ASR_SMOKE") != "1",
        reason="Real ASR smoke requires CADENCE_ASR_SMOKE=1 environment variable",
    )
    def test_real_asr_smoke(self):
        try:
            import whisper
        except ImportError:
            pytest.skip("whisper not installed; cannot run real ASR smoke")

        if not CachedWhisperTranscriber.find_cached_model("base"):
            pytest.skip("Whisper base model not cached in ~/.cache/whisper/")

        audio_path = "/tmp/live_test_audio/pd_real_chunk_a.wav"
        if not os.path.exists(audio_path):
            pytest.skip(f"Audio file not found at {audio_path}")

        transcriber = CachedWhisperTranscriber(model_size="base")
        res = transcriber(audio_path)
        assert res.model_id == "whisper-base"
        assert isinstance(res.words, list)
        print(f"\nReal ASR transcribed {len(res.words)} words with confidence {res.overall_confidence:.2f}")


def test_exact_cached_path_is_loaded_and_official_alignment_heads_restored(monkeypatch):
    mock_whisper = MagicMock()
    mock_whisper._ALIGNMENT_HEADS = {'base': b'known-base-heads'}
    with patch.dict(sys.modules, {'whisper':mock_whisper}):
        monkeypatch.setattr(CachedWhisperTranscriber, 'find_cached_model',
                            staticmethod(lambda model:'/checked/cache/base.pt'))
        CachedWhisperTranscriber(model_size='base',device='cpu')
    assert mock_whisper.load_model.call_args.kwargs['name'] == '/checked/cache/base.pt'
    assert mock_whisper.load_model.call_args.kwargs['device'] == 'cpu'
    mock_whisper.load_model.return_value.set_alignment_heads.assert_called_once_with(b'known-base-heads')
