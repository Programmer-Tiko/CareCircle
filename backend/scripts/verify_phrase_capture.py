"""Opt-in real cached-ASR passage gate over HTTP and isolated local PostgreSQL.

Uses a supplied fixed-passage WAV and different-content WAV. Synthetic positive
speech is appropriate for software checks, never clinical/patient validation.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/scripts'))
from app.api import main as api
from verify_live_workflow import serve


def run(args):
    url=os.environ['TEST_CONVERSATION_DB_URL'];schema='phrase_gate_'+uuid4().hex
    with psycopg.connect(url) as db:db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect():return psycopg.connect(url,row_factory=dict_row,options=f'-csearch_path={schema},public')
    try:
        with connect() as db:
            ddl=(ROOT/'backend/app/api/schema.sql').read_text()
            db.execute('\n'.join(line for line in ddl.splitlines() if not line.startswith(('CREATE EXTENSION','SELECT create_hypertable'))))
        app=api.create_app()
        def database():
            with connect() as db:yield db
        app.dependency_overrides[api.get_db]=database
        with serve(app) as client:
            data=args.expected.read_bytes()
            result=client.post('/profiles/phrase/enroll?experimental=true&verify_passage=true',
                data={'condition':'parkinsons'},files=[('files',(f'reference{i}.wav',data,'audio/wav')) for i in range(3)])
            assert result.status_code==200,result.status_code
            good=client.post('/profiles/phrase/checkin?experimental=true&verify_passage=true',files={'file':('reading.wav',data,'audio/wav')})
            assert good.status_code==200,good.status_code
            evidence=good.json()['measured']['phrase_evidence']
            assert evidence['status']=='available' and evidence['phrase_match']=='matched'
            bad=client.post('/profiles/phrase/checkin?verify_passage=true',files={'file':('wrong.wav',args.different.read_bytes(),'audio/wav')})
            assert bad.status_code==422,bad.status_code
            history=client.get('/profiles/phrase/history').json()
            assert len(history['checkins'])==1
            assert history['checkins'][0]['measured']['phrase_evidence']==evidence
        report={'result':'PASS','transport':'real localhost HTTP + local PostgreSQL + cached Whisper base',
            'positive_fixture':'supplied fixed-passage recording','negative_fixture':'supplied different-content recording',
            'reference_take_count':3,'positive_checkin_status':good.status_code,'negative_checkin_status':bad.status_code,
            'phrase_match':evidence['phrase_match'],'alignment_available':evidence['alignment_available'],
            'persisted_checkins_after_negative':1,'comparability':evidence['comparability']}
    finally:
        with psycopg.connect(url) as db:db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    report['test_schema_removed']=True
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected',type=Path,required=True);parser.add_argument('--different',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
