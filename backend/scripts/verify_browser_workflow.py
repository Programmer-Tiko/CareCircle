"""Opt-in real Chrome simulated-microphone / Tiger Cloud test. See docs/END-TO-END-STATUS.md."""
import sys,os,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'backend'));sys.path.insert(0,str(Path.cwd()/'backend/scripts'))
from verify_live_workflow import serve
from app.api import main as api
from fastapi.responses import HTMLResponse
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from uuid import uuid4
from io import BytesIO
import numpy as np,soundfile as sf
schema='cadence_browser_'+uuid4().hex
url=os.environ['TIGER_DATA_URL']
def connect():return psycopg.connect(url,row_factory=dict_row,options=f'-csearch_path={schema},public',connect_timeout=15)
with psycopg.connect(url,connect_timeout=15) as db:db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
try:
 with connect() as db:db.execute(Path('backend/app/api/schema.sql').read_text())
 app=api.create_app()
 def dep():
  with connect() as db:yield db
 app.dependency_overrides[api.get_db]=dep
 @app.get('/capture-proof',response_class=HTMLResponse)
 def page():return Path('browser-capture.html').read_text()
 audio,rate=sf.read('backend/tests/fixtures/speech_chunk.wav')
 path=Path('/private/tmp/cadence-browser-deviant.wav');sf.write(path,np.concatenate([audio,np.zeros(rate*4),audio]),rate)
 with serve(app) as client:
  env={**os.environ,'CADENCE_BROWSER_URL':str(client.base_url).rstrip('/'),'CADENCE_MIC_WAV':str(Path('backend/tests/fixtures/speech_chunk.wav').resolve()),'CADENCE_DEVIANT_WAV':str(path)}
  run=subprocess.run(['node',str(Path('backend/scripts/browser_capture_smoke.cjs').resolve())],env=env,capture_output=True,text=True,timeout=180)
  if run.returncode:print(run.stderr);raise RuntimeError('Browser test failed')
  report=json.loads(run.stdout.strip());report['storage']='isolated real Tiger Cloud schema'
  Path('docs/BROWSER-WORKFLOW-VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
finally:
 with psycopg.connect(url,connect_timeout=15) as db:db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
