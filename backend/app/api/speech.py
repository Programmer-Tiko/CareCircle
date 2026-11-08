"""Optional local ASR transport; no provider upload or implicit model download.

Use Python 3.11 or 3.12 with requirements-asr.txt and cached Whisper
weights. ASR is opt-in via CADENCE_ASR_ENABLED=true. Imports do not load weights.
Phrase matching supplies evidence only; it cannot certify comparable capture.
"""
from dataclasses import asdict
from functools import lru_cache
import math
import os
import re
from tempfile import TemporaryDirectory
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import Depends, File, HTTPException, UploadFile
import soundfile as sf
import numpy as np

from app.audio.alignment_validation import validate_word_timestamp
from app.audio.phrase_alignment import verify_phrase
from app.passage import PASSAGE_ID

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_LOAD_LOCK = Lock()
_INFERENCE_LOCK = Lock()


def asr_enabled() -> bool:
    return os.getenv('CADENCE_ASR_ENABLED', '').strip().lower() in ('1', 'true', 'yes', 'on')


class _SerializedTranscriber:
    def __init__(self, transcriber):
        self.transcriber = transcriber

    def __call__(self, wav_path):
        # One shared lock covers calls from both /transcribe and phrase evidence.
        with _INFERENCE_LOCK:
            return self.transcriber(wav_path)


@lru_cache(maxsize=2)
def _cached_transcriber(model: str):
    from app.audio.whisper_adapter import CachedWhisperTranscriber
    return _SerializedTranscriber(CachedWhisperTranscriber(model_size=model))


def get_transcriber():
    """Return a lazily loaded, inference-serialized cached-only local model.

    Raises HTTP 503 when disabled, misconfigured, dependencies/checkpoint are
    unavailable, or the local model cannot load. Never falls back to a download.
    """
    if not asr_enabled():
        raise HTTPException(503, 'Local speech recognition is disabled. Set CADENCE_ASR_ENABLED=true to enable it.')
    model = os.getenv('CADENCE_WHISPER_MODEL', 'base').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}', model) or '..' in model:
        raise HTTPException(503, 'CADENCE_WHISPER_MODEL must be a model name, not a file path.')
    try:
        # lru_cache alone can construct twice under concurrent cache misses.
        with _LOAD_LOCK:
            return _cached_transcriber(model)
    except Exception as exc:
        raise HTTPException(503, 'Local ASR unavailable. Use Python 3.11 or 3.12 with requirements-asr.txt and pre-cached model weights.') from exc


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def phrase_evidence(wav_path: str) -> dict:
    """Return explicit phrase evidence for optional enrollment/check-in use.

    Root API policy decides what to do with matched/mismatch/uncertain. Matching
    does not validate device, channel, audio quality or any health interpretation.
    ASR unavailability is metadata, never fabricated matching evidence.
    """
    unavailable = {
        'available': False, 'passage_id': PASSAGE_ID, 'phrase_match': 'uncertain',
        'alignment_available': False, 'comparability': {'overall': 'not_assessed'},
    }
    try:
        transcriber = get_transcriber()
    except HTTPException as exc:
        return {**unavailable, 'status': 'disabled' if not asr_enabled() else 'unavailable', 'reason': exc.detail}
    try:
        result = verify_phrase(wav_path, transcriber)
        return {
            **_json_safe(asdict(result)), 'available': True, 'status': 'available', 'passage_id': PASSAGE_ID,
            'comparability': {
                'phrase': result.phrase_match, 'overall': 'not_assessed',
                'reason': 'Phrase evidence does not establish comparable device, channel, recording quality, or health status.',
            },
        }
    except Exception:
        return {**unavailable, 'status': 'failed', 'reason': 'Local ASR phrase analysis failed; passage could not be assessed.'}


def _response(result):
    if not math.isfinite(result.overall_confidence) or not 0 <= result.overall_confidence <= 1:
        raise HTTPException(502, 'Local ASR returned invalid confidence evidence.')
    words = []
    for word in result.words:
        validity = validate_word_timestamp(word)
        if not validity.text_usable:
            continue
        if not validity.timestamps_usable or not validity.confidence_usable:
            raise HTTPException(502, 'Local ASR returned invalid word evidence.')
        words.append(asdict(word))
    text = ' '.join(word['word'].strip() for word in words).strip()
    if not text:
        raise HTTPException(422, 'No speech was recognized. Record again in a quiet room, or type your answer.')
    return {'text': text, 'words': words, 'needs_review': True,
            'review_notice': 'Automatic transcription can be wrong. Review and edit before sending.',
            'overall_confidence': result.overall_confidence, 'model_id': result.model_id}


def install_routes(app):
    @app.post('/transcribe')
    def transcribe(file: Annotated[UploadFile, File()], transcriber=Depends(get_transcriber)):
        try:
            with TemporaryDirectory(prefix='cadence-asr-') as directory:
                path = Path(directory) / 'capture.wav'
                size = 0
                with path.open('wb') as target:
                    while chunk := file.file.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise HTTPException(413, 'WAV upload exceeds 20 MiB.')
                        target.write(chunk)
                try:
                    info = sf.info(path)
                    if info.format not in ('WAV', 'WAVEX') or info.frames == 0:
                        raise ValueError('Expected nonempty WAV.')
                    if not .25 <= info.duration <= 120 or info.channels not in (1, 2) or not 8000 <= info.samplerate <= 96000:
                        raise ValueError('Unsupported recording dimensions.')
                except (ValueError, sf.LibsndfileError):
                    raise HTTPException(400, 'Upload a valid mono/stereo WAV recording, 0.25 to 120 seconds long.') from None
                samples, _ = sf.read(path, dtype='float32', always_2d=True)
                if not np.isfinite(samples).all() or float(np.max(np.abs(samples))) < .0001:
                    raise HTTPException(422, 'The recording is silent or invalid. Check the microphone, record again, or type your answer.')
                if float(np.mean(np.abs(samples) >= .99)) > .2:
                    raise HTTPException(422, 'The recording is heavily distorted. Move away from the microphone and try again, or type your answer.')
                try:
                    return _response(transcriber(str(path)))
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(502, 'Local transcription failed.') from exc
        finally:
            file.file.close()
