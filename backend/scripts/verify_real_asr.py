"""Real cached-ASR smoke in an optional Whisper-capable environment.

Pass a WAV of the fixed passage and a different-content WAV. No model download
is allowed. Synthetic positive audio verifies transport/recognition only, not
clinical performance. Does not install anything or change the live API.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.audio.whisper_adapter import CachedWhisperTranscriber
from app.audio.phrase_alignment import verify_phrase


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-wav',type=Path,required=True)
    parser.add_argument('--different-wav',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    import whisper
    import torch
    def forbidden(*args,**kwargs):raise RuntimeError('Model-weight downloads forbidden during smoke')
    whisper._download=forbidden
    torch.set_num_threads(2)
    started=time.monotonic();transcriber=CachedWhisperTranscriber('base',device='cpu')
    recordings=[]
    for label,path in [('expected_passage',args.expected_wav),('different_content',args.different_wav)]:
        result=verify_phrase(str(path),transcriber)
        recordings.append({'fixture':label,'result':asdict(result)})
    assert recordings[0]['result']['phrase_match']=='matched'
    assert recordings[1]['result']['phrase_match']!='matched'
    report={'scope':'Real cached Whisper base ASR; supplied positive/negative fixtures, not clinical validation',
            'weight_downloads':'blocked by download guard','model_reuse':'one transcriber instance',
            'elapsed_seconds':time.monotonic()-started,'recordings':recordings,'result':'PASS'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'result':'PASS','recordings':len(recordings),'output':str(args.output)}))


if __name__=='__main__':main()
