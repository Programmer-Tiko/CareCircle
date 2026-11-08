"""Verify constructed fragmentation on existing real-speech chunks, not clinical efficacy.

python scripts/verify_fragmentation.py --audio-dir /tmp/live_test_audio --output /tmp/fragmentation.json
Does not download, commit or label constructed recordings as patient outcomes.
"""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.audio.vad import detect_speech_segments
from app.models.personal_baseline import fit_baseline, PersistentDeviationTracker
from app.passage import PASSAGE_SYLLABLE_COUNT
from app.pipeline import build_take_from_audio, evaluate_checkin


def verify(audio_dir):
    a, sr = sf.read(audio_dir / 'pd_real_chunk_a.wav')
    b, sr_b = sf.read(audio_dir / 'pd_real_chunk_b.wav')
    assert sr == sr_b
    with TemporaryDirectory(prefix='cadence-fragmentation-') as directory:
        root = Path(directory)
        refs=[]
        for i,(parts,gap) in enumerate([([a,b],.5),([b,a],.6),([a,a],.55),([b,b],.65)]):
            path=root/f'ref{i}.wav'
            sf.write(path,np.concatenate([parts[0],np.zeros(round(gap*sr)),parts[1]]),sr)
            assert len(detect_speech_segments(path))==2
            refs.append(build_take_from_audio(str(path),PASSAGE_SYLLABLE_COUNT))
        stats=fit_baseline(refs)
        # Preserve the same a+b speech content as reference 0; only insert
        # internal silence, rather than shorten the reading or change its words.
        pieces=list(np.array_split(a,3))+list(np.array_split(b,3))
        waveform=np.concatenate([v for i,piece in enumerate(pieces)
            for v in ([piece,np.zeros(round(.6*sr))] if i<len(pieces)-1 else [piece])])
        path=root/'fragmented.wav';sf.write(path,waveform,sr)
        segments=detect_speech_segments(path)
        assert len(segments)==6, segments
        take=build_take_from_audio(str(path),PASSAGE_SYLLABLE_COUNT)
        assert take['mean_speech_segment_duration'] < min(t['mean_speech_segment_duration'] for t in refs)
        assert stats.mad['mean_speech_segment_duration'] > .01  # no floor-driven enormous z-score
        tracker=PersistentDeviationTracker(2.,2)
        first=evaluate_checkin(str(path),stats,tracker,'parkinsons',PASSAGE_SYLLABLE_COUNT)
        second=evaluate_checkin(str(path),stats,tracker,'parkinsons',PASSAGE_SYLLABLE_COUNT)
        assert not first.triggered and second.triggered
        assert second.feature_scores['mean_speech_segment_duration'] < -2.
        return {'scope':'constructed fragmentation of existing real-speech chunks; software verification only',
                'gap_seconds':.6,'expected_segments':6,'detected_segments':segments,
                'reference_features':refs,'fragmented_features':take,
                'baseline_median':stats.median,'baseline_mad':stats.mad,
                'first':first.__dict__,'second':second.__dict__,'result':'PASS'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.audio_dir)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
