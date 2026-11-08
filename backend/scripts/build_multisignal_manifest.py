"""Build a manifest from the project's verified reading-task layouts.

Italian inputs must be the flattened B1-only pd_00.wav/hc_00.wav directories
used in the existing replication. Do not point at a mixed-task dataset root.
One file per person is required; alternate/repeated recordings need an explicit
manual manifest with their true shared subject_id.
"""
import argparse
import csv
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mdvr-dir',type=Path,required=True)
    parser.add_argument('--italian-b1-pd',type=Path)
    parser.add_argument('--italian-b1-hc',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=[]
    for group,label in [('PD',1),('HC',0)]:
        paths=sorted((args.mdvr_dir/group).glob('*.wav'))
        if not paths: parser.error(f'No reading WAVs in {args.mdvr_dir/group}')
        for path in paths:
            match=re.fullmatch(r'(ID\d+)_(pd|hc)_\d+_\d+_\d+',path.stem)
            if not match or match[2]!=group.lower(): parser.error(f'Unexpected MDVR filename: {path}')
            rows.append({'path':str(path.resolve()),'subject_id':'mdvr_'+match[1],'label':label,'dataset':'mdvr_kcl'})
    if bool(args.italian_b1_pd)!=bool(args.italian_b1_hc): parser.error('Provide both Italian B1 directories.')
    for directory,group,label in [(args.italian_b1_pd,'pd',1),(args.italian_b1_hc,'hc',0)]:
        if directory is None: continue
        paths=sorted(directory.glob('*.wav'))
        if not paths: parser.error(f'No B1 WAVs in {directory}')
        for path in paths:
            if not re.fullmatch(group+r'_\d+',path.stem):
                parser.error(f'Expected verified flattened B1 layout, not guessed subject IDs: {path}')
            rows.append({'path':str(path.resolve()),'subject_id':'italian_b1_'+path.stem,'label':label,'dataset':'italian_b1'})
    ids=[r['subject_id'] for r in rows]
    if len(ids)!=len(set(ids)): parser.error('Repeated participant: provide an explicit grouped manifest.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('w') as target:
        writer=csv.DictWriter(target,fieldnames=['path','subject_id','label','dataset'])
        writer.writeheader();writer.writerows(rows)
    print(f'Wrote {len(rows)} records to {args.output}; passage counts deliberately unavailable.')


if __name__=='__main__': main()
