"""Local voice development server; no browser launch and no demo-profile seeding."""
import argparse
import os
from pathlib import Path
import socket
import sys
from urllib.parse import urlsplit


def question_demo_selector(context):
    """Explicit demo seam: real eligibility/templates/validation; simulated model ID choice."""
    import json
    from app.dialogue.conversation_adapter import selector_adapter
    def choose(prompt):
        payload = json.loads(prompt)
        unit = payload['eligible_questions'][0]
        return json.dumps({'selected_question_id': unit['id'], 'evidence_ids': [unit['id']],
                           'patient_quote': payload['patient_answer'], 'abstain': False})
    return selector_adapter(context, model_call=choose)


def create_voice_app(offline_demo=False):
    from app.api.main import create_app
    app = create_app()
    if offline_demo:
        from app.api.conversations import get_selector
        app.dependency_overrides[get_selector] = lambda: question_demo_selector
        app.state.question_selection_mode = 'offline-demo'
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--settings-file', type=Path)
    parser.add_argument('--cache-path', type=Path, required=True)
    parser.add_argument('--model', default='base.en')
    parser.add_argument('--offline-question-demo', action='store_true',
                        help='Explicitly simulate model ID choice; retain real retrieval, speech, safety and SQL.')
    args = parser.parse_args()
    parsed = urlsplit(args.db_url)
    database_name = 'cadence_voice_first_demo' if args.offline_question_demo else 'cadence_voice_first'
    if (parsed.scheme != 'postgresql' or parsed.hostname != '127.0.0.1'
            or parsed.username != 'postgres' or parsed.password is not None
            or parsed.path != '/' + database_name or not parsed.port
            or parsed.query or parsed.fragment):
        parser.error('Use the dedicated passwordless localhost ' + database_name + ' database.')
    if args.port != 0 and not 1024 <= args.port <= 65535:
        parser.error('Choose an application port between 1024 and 65535, or 0 for an available port.')
    # Set the isolated database before loading optional provider configuration.
    # dotenv override=False cannot replace it with a cloud/older demo database.
    for name in list(os.environ):
        if name.startswith('PG'):
            os.environ.pop(name, None)
    os.environ['PGPASSFILE'] = os.devnull
    os.environ['PGSERVICEFILE'] = os.devnull
    os.environ['PGSSLMODE'] = 'disable'
    os.environ['TIGER_DATA_URL'] = args.db_url
    if args.settings_file:
        if not args.settings_file.is_file():
            parser.error('The optional settings file does not exist.')
        from dotenv import load_dotenv
        load_dotenv(args.settings_file, override=False)
    os.environ['CADENCE_ASR_ENABLED'] = 'true'
    os.environ['CADENCE_WHISPER_MODEL'] = args.model
    os.environ['CADENCE_WHISPER_CACHE'] = str(args.cache_path.resolve())
    # The backend owns the default voice. Do not shadow ELEVENLABS_VOICE_ID
    # with a launcher default when a legacy override is configured.
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'backend'))
    import uvicorn
    app = create_voice_app(args.offline_question_demo)
    # Bind before reporting the URL. Port 0 is safe when another rehearsal is
    # already running; the OS selects a free localhost port without stopping it.
    with socket.socket() as listener:
        try:
            listener.bind(('127.0.0.1', args.port))
        except OSError:
            parser.error('Application port unavailable. Keep the existing server; choose another --port or --port 0.')
        port = listener.getsockname()[1]
        print(f'Cadence voice development: http://127.0.0.1:{port}/', flush=True)
        print('Open this URL manually in your regular Chrome browser. No fake media devices or fixture audio.', flush=True)
        print('ASR: cached local Whisper. TTS: ElevenLabs when configured, otherwise labeled browser voice.', flush=True)
        print('OFFLINE QUESTION DEMO: model ID choice is simulated; no live Groq calls.' if args.offline_question_demo else
              'Live Groq mode: evidence-guided selection; missing credentials or failure preserves uncertainty.', flush=True)
        server = uvicorn.Server(uvicorn.Config(app, access_log=False))
        server.run(sockets=[listener])


if __name__ == '__main__':
    main()
