"""Measurement behavior and capture confounds; no patient-performance claims."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.audio.prosody_features import extract_prosody_features


def waveform(frequency, amplitude=0.15, rate=16000, seconds=3):
    t = np.arange(round(rate * seconds)) / rate
    freq = frequency(t) if callable(frequency) else np.full(len(t), frequency)
    amp = amplitude(t) if callable(amplitude) else amplitude
    return amp * np.sin(2 * np.pi * np.cumsum(freq) / rate)


def measure(tmp_path, data, rate=16000):
    path = tmp_path / 'probe.wav'
    sf.write(path, data, rate, subtype='FLOAT')
    result = extract_prosody_features(path)
    json.dumps(result, allow_nan=False)
    return result


def test_pitch_modulation_has_wider_spread_than_stationary_tone(tmp_path):
    flat = measure(tmp_path, waveform(160))
    varied = measure(tmp_path, waveform(lambda t: 160 * 2 ** (3 * np.sin(2*np.pi*t) / 12)))
    assert flat['metrics']['f0_spread_semitones'] < .1
    assert varied['metrics']['f0_spread_semitones'] > 4.5
    assert not varied['quality_flags']


def test_energy_variability_gain_invariance_and_modulation(tmp_path):
    data = waveform(160, lambda t: .12 * (1 + .6 * np.sin(2*np.pi*t)))
    original = measure(tmp_path, data)
    quieter = measure(tmp_path, data * .2)
    spread = original['metrics']['voiced_energy_spread_db']
    assert spread > 8
    assert quieter['metrics']['voiced_energy_spread_db'] == pytest.approx(spread, abs=.02)
    assert quieter['metrics']['f0_spread_semitones'] == pytest.approx(original['metrics']['f0_spread_semitones'], abs=.02)


def test_silence_has_no_spurious_pitch_or_energy_measurement(tmp_path):
    result = measure(tmp_path, np.zeros(16000))
    assert result['metrics']['voiced_fraction'] == 0
    assert result['metrics']['f0_spread_semitones'] is None
    assert result['metrics']['voiced_energy_spread_db'] is None
    assert 'insufficient_voicing' in result['quality_flags']


def test_clipped_audio_and_antiphase_channels_are_flagged(tmp_path):
    clipped = measure(tmp_path, np.clip(waveform(160, 3), -1, 1))
    assert 'clipping' in clipped['quality_flags']
    assert clipped['metrics']['f0_spread_semitones'] is None
    signal = waveform(160)
    cancelled = measure(tmp_path, np.column_stack((signal, -signal)))
    assert 'channel_cancellation' in cancelled['quality_flags']
    assert cancelled['metrics']['voiced_energy_spread_db'] is None


def test_short_recording_and_parameter_validation(tmp_path):
    result = measure(tmp_path, np.ones(160))
    assert 'recording_too_short' in result['quality_flags']
    with pytest.raises(ValueError):
        extract_prosody_features(tmp_path / 'probe.wav', f0_floor=500, f0_ceiling=100)


def test_resampling_same_tone_preserves_pitch_spread(tmp_path):
    low = measure(tmp_path, waveform(lambda t: 180 * 2 ** (2 * np.sin(2*np.pi*t) / 12), rate=16000), 16000)
    high = measure(tmp_path, waveform(lambda t: 180 * 2 ** (2 * np.sin(2*np.pi*t) / 12), rate=44100), 44100)
    assert low['metrics']['f0_spread_semitones'] == pytest.approx(high['metrics']['f0_spread_semitones'], abs=.05)


def test_silence_padding_changes_voiced_fraction_not_inferred_health(tmp_path):
    signal = waveform(160, seconds=1)
    voiced = measure(tmp_path, signal)
    padded = measure(tmp_path, np.concatenate((np.zeros(16000), signal, np.zeros(16000))))
    assert voiced['metrics']['voiced_fraction'] > .9
    assert padded['metrics']['voiced_fraction'] < .5
