"""Download a small, reproducible ItalianPVS sample and export acoustic graphs.

Requires numpy, scipy, matplotlib. Run this file with Python; no training occurs.
"""
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen
import csv
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from scipy import signal

ROOT = Path(__file__).resolve().parent
REPO = 'birgermoell/Italian_Parkinsons_Voice_and_Speech'
API = 'https://huggingface.co/api/datasets/' + REPO


def get_json(url):
    with urlopen(url, timeout=60) as response:
        return json.load(response)


def main():
    for directory in ('raw', 'plots', 'arrays'):
        (ROOT / directory).mkdir(exist_ok=True)
    revision_file = ROOT / 'revision.txt'
    if revision_file.exists():
        revision = revision_file.read_text().strip()
    else:
        revision = get_json(API)['sha']
        revision_file.write_text(revision + '\n')
    listing = get_json(API + '/tree/' + revision + '/italian_parkinson?recursive=true&limit=1000')
    # This corpus fits in one page; reject an incomplete listing rather than sample silently.
    if len(listing) >= 1000:
        raise RuntimeError('Listing needs pagination before sampling.')
    selected = []
    for group, label in [('22 Elderly Healthy Control', 'HC'),
                         ("28 People with Parkinson's disease", 'PD')]:
        candidates = [item for item in listing if item['path'].endswith('.wav')
                      and ('/' + group + '/') in item['path']]
        subjects = sorted({str(Path(item['path']).parent) for item in candidates})
        chosen = 0
        for subject in subjects:
            tasks = []
            for prefix in ('B1', 'VA1'):
                matches = sorted([item for item in candidates
                                  if str(Path(item['path']).parent) == subject
                                  and Path(item['path']).name.upper().startswith(prefix)],
                                 key=lambda item: item['path'])
                if not matches:
                    break
                tasks.append((prefix, matches[0]))
            if len(tasks) == 2:
                chosen += 1
                selected.extend((label, f'{label}_{chosen:02d}', task, item)
                                for task, item in tasks)
            if chosen == 3:
                break
        if chosen != 3:
            raise RuntimeError('Could not find three subjects with both task codes in ' + group)
    rows = []
    overview, axes = plt.subplots(6, 2, figsize=(16, 16), constrained_layout=True)
    for label, subject, task, item in selected:
        sample = subject + '_' + task
        url = 'https://huggingface.co/datasets/' + REPO + '/resolve/' + revision + '/' + quote(item['path'], safe='/')
        target = ROOT / 'raw' / (sample + '.wav')
        expected_hash = item.get('lfs', {}).get('oid')
        if not target.exists():
            with urlopen(url, timeout=90) as response:
                payload = response.read(25_000_001)
            if len(payload) > 25_000_000:
                raise RuntimeError('Unexpectedly large sample')
            if len(payload) != item['size']:
                raise RuntimeError('Download size mismatch')
            if expected_hash and hashlib.sha256(payload).hexdigest() != expected_hash:
                raise RuntimeError('Source checksum mismatch')
            target.write_bytes(payload)
        checksum = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected_hash and checksum != expected_hash:
            raise RuntimeError('Cached audio checksum mismatch')
        rate, raw = wavfile.read(target)
        original_channels = 1 if raw.ndim == 1 else raw.shape[1]
        if np.issubdtype(raw.dtype, np.integer):
            if raw.dtype == np.uint8:
                audio = (raw.astype(float) - 128) / 128
            else:
                audio = raw.astype(float) / float(2 ** (np.iinfo(raw.dtype).bits - 1))
        else:
            audio = raw.astype(float)
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        if not np.isfinite(audio).all() or len(audio) < rate * .05:
            raise RuntimeError('Invalid or too short audio')
        times = np.arange(len(audio)) / rate
        frame = min(len(audio), round(rate * .025))
        hop = max(1, round(rate * .010))
        frequencies, frame_times, psd = signal.spectrogram(
            audio, fs=rate, window='hann', nperseg=frame,
            noverlap=frame-hop, detrend=False, scaling='density', mode='psd')
        db = 10 * np.log10(np.maximum(psd, 1e-12))
        starts = np.arange(0, len(audio)-frame+1, hop)
        rms = np.array([np.sqrt(np.mean(audio[s:s+frame] ** 2)) for s in starts])
        rms_times = (starts + frame / 2) / rate
        np.savez_compressed(ROOT / 'arrays' / (sample + '.npz'),
                            frequency_hz=frequencies, time_s=frame_times,
                            psd=psd, psd_db=db, rms_time_s=rms_times, rms=rms,
                            sample_rate_hz=rate)
        fig, panels = plt.subplots(3, 1, figsize=(12, 8), constrained_layout=True)
        stride = max(1, len(audio)//100000)
        panels[0].plot(times[::stride], audio[::stride], lw=.4)
        panels[0].set(ylabel='Amplitude (full scale)', ylim=(-1, 1))
        image = panels[1].pcolormesh(frame_times, frequencies, db, shading='auto',
                                    cmap='magma', vmin=-120, vmax=-20)
        panels[1].set(ylabel='Frequency (Hz)', ylim=(0, min(8000, rate/2)))
        fig.colorbar(image, ax=panels[1], label='PSD (dB re 1 FS²/Hz)')
        panels[2].plot(rms_times, rms)
        panels[2].set(ylabel='RMS (full scale)', xlabel='Time (seconds)', ylim=(0, 1))
        fig.suptitle(f'ItalianPVS | {sample} | source task code {task} | {rate} Hz')
        fig.savefig(ROOT / 'plots' / (sample + '.png'), dpi=160)
        plt.close(fig)
        row = (0 if label == 'HC' else 3) + int(subject[-2:])-1
        col = 0 if task == 'B1' else 1
        axes[row, col].pcolormesh(frame_times, frequencies, db, shading='auto',
                                 cmap='magma', vmin=-120, vmax=-20)
        axes[row, col].set(title=sample, xlabel='Time (s)', ylabel='Hz',
                           ylim=(0, min(8000, rate/2)))
        rows.append(dict(sample_id=sample, subject_id=subject, label=label,
                         source_task_code=task, source_path=item['path'], source_url=url,
                         sha256=checksum, sample_rate_hz=rate, channels=original_channels,
                         duration_s=len(audio)/rate, size_bytes=target.stat().st_size,
                         peak_abs=float(np.max(np.abs(audio))), rms=float(np.sqrt(np.mean(audio**2)))))
        print(f'{sample}: {len(audio)/rate:.2f}s, {rate} Hz; verified and plotted', flush=True)
    overview.suptitle('ItalianPVS pilot: elderly controls and Parkinson\'s | fixed PSD color scale -120 to -20 dB\nDescriptive plots only; task codes retained from source filenames', fontsize=14)
    overview.savefig(ROOT / 'plots' / 'comparison.png', dpi=160)
    plt.close(overview)
    with (ROOT / 'manifest.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Done: {len(rows)} recordings; {sum(r["size_bytes"] for r in rows)/1e6:.1f} MB', flush=True)


if __name__ == '__main__':
    main()
