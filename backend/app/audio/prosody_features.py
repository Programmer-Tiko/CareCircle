"""Experimental waveform prosody measurements, independent of VAD timing.

Not used by the live trigger. These are capture-dependent acoustic observations,
not Parkinson's severity or diagnosis. Compare only the same phrase/device/setup.
Praat autocorrelation supplies an F0 estimate; transparent statistics summarize
its voiced frames. No pooled patient model is trained or called here.
"""
from pathlib import Path

import numpy as np
import parselmouth
import soundfile as sf


def extract_prosody_features(
    wav_path: str | Path, *, f0_floor: float = 60.0, f0_ceiling: float = 500.0,
    frame_step: float = 0.01,
) -> dict:
    """Return JSON-compatible metrics, parameters and explicit quality flags.

    F0 spread is p90-p10 of log2(F0), in semitones. Energy spread is p90-p10
    of frame RMS in dB, measured only at voiced-frame centers: constant gain
    cancels, but AGC/compression, distance changes and noise still confound it.
    Voiced fraction includes silence and must not be called an intelligibility
    score. Frame-wise octave jumps are flagged; sufficiently frequent jumps
    suppress the F0 spread rather than silently reporting a false wide range.
    This uses Praat raw autocorrelation (not filtered autocorrelation); a stable
    octave error may escape the jump heuristic. There is no claim that quality
    flags identify every tracking failure or that silence is pathology.
    """
    if not (0 < f0_floor < f0_ceiling) or not (0.005 <= frame_step <= 0.05):
        raise ValueError('Require 0 < f0_floor < f0_ceiling and frame_step in [0.005, 0.05].')
    audio, sample_rate = sf.read(str(wav_path), dtype='float64', always_2d=True)
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError('Audio must be nonempty and finite.')
    flags = []
    clipping_fraction = float(np.mean(np.abs(audio) >= 0.999))
    if clipping_fraction > 0.001:
        flags.append('clipping')
    mono = audio.mean(axis=1)
    channel_rms = float(np.sqrt(np.mean(audio ** 2)))
    mono_rms = float(np.sqrt(np.mean(mono ** 2)))
    if audio.shape[1] > 1 and channel_rms > 1e-7 and mono_rms < channel_rms * 0.1:
        flags.append('channel_cancellation')
    metrics = {'f0_spread_semitones': None, 'voiced_energy_spread_db': None,
               'voiced_fraction': 0.0, 'pitch_octave_jump_fraction': None}
    details = {'sample_rate': sample_rate, 'channels': audio.shape[1],
               'duration_seconds': len(mono) / sample_rate,
               'clipping_fraction': clipping_fraction, 'pitch_frames': 0, 'voiced_frames': 0}
    parameters = {'pitch_method': 'praat_raw_autocorrelation',
                  'energy_window_seconds': 0.04, 'f0_floor_hz': f0_floor, 'f0_ceiling_hz': f0_ceiling,
                  'frame_step_seconds': frame_step, 'minimum_voiced_frames': 20,
                  'pitch_jump_threshold_semitones': 9.0, 'maximum_jump_fraction': 0.05}
    if len(mono) / sample_rate < max(0.1, 3 / f0_floor):
        flags.extend(['recording_too_short', 'insufficient_voicing'])
        return {'experimental': True, 'metrics': metrics, 'quality_flags': flags,
                'capture': details, 'parameters': parameters}
    sound = parselmouth.Sound(mono, sampling_frequency=sample_rate)
    pitch = sound.to_pitch_ac(time_step=frame_step, pitch_floor=f0_floor,
                              pitch_ceiling=f0_ceiling)
    frequencies = pitch.selected_array['frequency']
    voiced = np.isfinite(frequencies) & (frequencies > 0)
    details['pitch_frames'] = int(len(frequencies))
    details['voiced_frames'] = int(voiced.sum())
    metrics['voiced_fraction'] = float(voiced.mean()) if len(voiced) else 0.0
    if voiced.sum() < 20:
        flags.append('insufficient_voicing')
    else:
        # Only adjacent voiced frames count: gaps must not invent pitch jumps.
        pair_mask = voiced[:-1] & voiced[1:]
        jumps = np.abs(12 * np.log2(frequencies[1:][pair_mask] / frequencies[:-1][pair_mask]))
        jump_fraction = float(np.mean(jumps > 9)) if len(jumps) else 0.0
        metrics['pitch_octave_jump_fraction'] = jump_fraction
        semitones = 12 * np.log2(frequencies[voiced])
        if jump_fraction > 0.05:
            flags.append('unstable_pitch_tracking')
        else:
            metrics['f0_spread_semitones'] = float(np.percentile(semitones, 90) - np.percentile(semitones, 10))
        # 40ms windows are long enough for stable RMS; use actual frame centers.
        half_window = round(0.02 * sample_rate)
        centers = np.round(pitch.xs()[voiced] * sample_rate).astype(int)
        rms = np.array([np.sqrt(np.mean(mono[max(0, c-half_window):min(len(mono), c+half_window)] ** 2))
                        for c in centers])
        valid_rms = rms[rms > np.finfo(float).tiny]
        if len(valid_rms):
            db = 20 * np.log10(valid_rms)
            metrics['voiced_energy_spread_db'] = float(np.percentile(db, 90) - np.percentile(db, 10))
    if 'clipping' in flags or 'channel_cancellation' in flags:
        # Distortion invalidates comparisons even if Praat produces numbers.
        metrics['f0_spread_semitones'] = None
        metrics['voiced_energy_spread_db'] = None
    return {'experimental': True, 'metrics': metrics, 'quality_flags': flags,
            'capture': details, 'parameters': parameters}
