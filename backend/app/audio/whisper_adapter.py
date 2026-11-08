"""Cached-only Whisper adapter for VoiceRadial/Cadence.

Provides ``CachedWhisperTranscriber`` — a drop-in replacement for the
``make_whisper_transcriber()`` closure in ``phrase_alignment.py`` that fixes
three issues with the original implementation:

1. **No implicit downloads**: The adapter checks for locally cached model
   weights *before* calling ``whisper.load_model()``.  If the checkpoint file
   is not present under ``~/.cache/whisper/``, a clear ``FileNotFoundError``
   is raised instead of silently downloading hundreds of megabytes.

2. **Load once**: The model is loaded at construction time and reused across
   every ``__call__`` invocation, avoiding the per-recording reload overhead
   of the original ``_transcribe()`` closure.

3. **Explicit opt-in**: Real ASR smoke tests are gated behind the
   ``CADENCE_ASR_SMOKE=1`` environment variable, not just the presence of
   the ``whisper`` package.

Limitations – Confidence Scores
-------------------------------
Whisper's per-word ``probability`` field is a *decoding probability* — the
softmax value the model assigned to the chosen token during beam search.
It is **not** a calibrated recognition-confidence score.  In particular:

* High probability does NOT reliably indicate correct transcription.
* Low probability does NOT reliably indicate misrecognition.
* Values are not comparable across models, languages, or audio conditions.
* These probabilities must **never** be interpreted as clinical-grade
  accuracy metrics for medical or diagnostic applications.

The adapter faithfully passes through these values in
``WordTimestamp.confidence`` for downstream visibility, but consumers MUST
treat them as uncalibrated model artifacts.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.audio.phrase_alignment import TranscriptionResult, WordTimestamp

# Standard whisper cache directory (matches openai-whisper's default).
_DEFAULT_CACHE_DIR = Path(os.getenv('CADENCE_WHISPER_CACHE', str(Path.home() / '.cache' / 'whisper')))


class CachedWhisperTranscriber:
    """Whisper-backed transcriber that requires a locally cached model.

    Does **not** download weights.  Loads the model once at construction time
    and reuses it for every subsequent ``__call__``.

    Limitations — confidence scores:
        The ``confidence`` field in each ``WordTimestamp`` is populated from
        Whisper's per-word ``probability``.  This is an uncalibrated decoding
        probability, **not** a clinical recognition-confidence metric.
        See module docstring for details.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str | None = None,
    ) -> None:
        """Load a cached Whisper model.

        Parameters
        ----------
        model_size:
            Whisper model variant (``"tiny"``, ``"base"``, ``"small"``, etc.).
        device:
            PyTorch device string (e.g. ``"cpu"``, ``"cuda:0"``).  ``None``
            lets Whisper choose automatically.

        Raises
        ------
        ImportError
            If ``openai-whisper`` is not installed.
        FileNotFoundError
            If the model weights are not already cached locally at
            ``~/.cache/whisper/{model_size}.pt``.
        """
        # --- guard: whisper importable? ---
        try:
            import whisper  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "openai-whisper is not installed.  Install it with:\n"
                "  pip install openai-whisper\n"
                "Then download the model weights manually before using "
                "this adapter."
            ) from exc

        # --- guard: model cached locally? ---
        cached_path = self.find_cached_model(model_size)
        if cached_path is None:
            raise FileNotFoundError(
                f"Whisper '{model_size}' model weights not found at "
                f"{_DEFAULT_CACHE_DIR / (model_size + '.pt')}.\n"
                "Download the weights manually (e.g. "
                "`python -c \"import whisper; whisper.load_model('base')\"`) "
                "before using CachedWhisperTranscriber."
            )

        # --- load model once ---
        self._model_size = model_size
        load_kwargs: dict = {
            # A named model enters Whisper's downloader even when a file
            # exists (e.g. checksum mismatch). An explicit path never does.
            "name": cached_path,
            "download_root": str(_DEFAULT_CACHE_DIR),
        }
        if device is not None:
            load_kwargs["device"] = device
        self._model = whisper.load_model(**load_kwargs)
        # Loading by path bypasses official model-name alignment-head setup.
        # Preserve the published per-model heads when this Whisper provides them.
        alignment_heads = getattr(whisper, '_ALIGNMENT_HEADS', {}).get(model_size)
        if alignment_heads is not None:
            self._model.set_alignment_heads(alignment_heads)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def __call__(self, wav_path: str) -> TranscriptionResult:
        """Transcribe a WAV file using the pre-loaded model.

        Parameters
        ----------
        wav_path:
            Path to a 16 kHz mono WAV file.

        Returns
        -------
        TranscriptionResult
            Word-level timestamps with **uncalibrated** confidence values.
            See the class/module docstrings for confidence caveats.
        """
        # Decode supported WAV locally through the existing audio loader. Passing
        # samples avoids a system FFmpeg dependency and never downloads codecs.
        from app.audio.vad import load_mono_16k
        audio = load_mono_16k(wav_path).numpy()
        raw = self._model.transcribe(
            audio,
            word_timestamps=True,
            language="en",
            fp16=False,
        )

        words: list[WordTimestamp] = []
        for seg in raw.get("segments", []):
            for w in seg.get("words", []):
                words.append(
                    WordTimestamp(
                        word=w["word"].strip(),
                        start=w["start"],
                        end=w["end"],
                        # NOTE: This is an uncalibrated decoding probability,
                        # NOT a clinical confidence score.
                        confidence=w.get("probability", 0.0),
                    )
                )

        # Aggregate confidence (same heuristic as the original code)
        segments = raw.get("segments", [])
        if words:
            overall = sum(w.confidence for w in words) / len(words)
        elif segments:
            probs = [1.0 - s.get("no_speech_prob", 0.5) for s in segments]
            overall = sum(probs) / len(probs)
        else:
            overall = 0.0

        return TranscriptionResult(
            words=words,
            overall_confidence=overall,
            model_id=f"whisper-{self._model_size}",
        )

    # --------------------------------------------------------------------- #
    # Static helpers
    # --------------------------------------------------------------------- #

    @staticmethod
    def find_cached_model(model_size: str) -> str | None:
        """Return the local path to cached weights, or ``None`` if not found.

        Checks the standard whisper cache directory:
        ``~/.cache/whisper/{model_size}.pt``
        """
        path = _DEFAULT_CACHE_DIR / f"{model_size}.pt"
        if path.is_file():
            return str(path)
        return None
