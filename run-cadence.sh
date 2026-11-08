#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
if [[ -x .venv-asr/bin/python ]]; then
  cadence_python=.venv-asr/bin/python
  export CADENCE_DEFAULT_ASR=true
elif [[ -x .venv/bin/python ]]; then
  cadence_python=.venv/bin/python
  export CADENCE_DEFAULT_ASR=false
else
  echo 'Create backend/.venv and install backend/requirements.txt first. See README.md.' >&2
  exit 1
fi
exec "$cadence_python" - <<'PY'
from dotenv import load_dotenv
import os
import uvicorn
load_dotenv('.env')
# Honor an explicit .env or shell preference; only choose a default if absent.
os.environ.setdefault('CADENCE_ASR_ENABLED', os.environ['CADENCE_DEFAULT_ASR'])
uvicorn.run('app.api.main:app', host='127.0.0.1', port=int(os.getenv('CADENCE_PORT','8000')))
PY
