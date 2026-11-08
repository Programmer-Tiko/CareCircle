"""Keep collection and tests independent of private configuration and services."""
import httpx
import os
import psycopg
import pytest
from urllib.parse import urlsplit


def pytest_addoption(parser):
    parser.addoption('--disposable-db-url', default=None,
                     help='Explicit localhost cadence_integration_test database; never loaded from dotenv.')
    parser.addoption('--browser-smoke', action='store_true',
                     help='Run the optional real-browser test against the disposable database.')


def _validate_disposable_database(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'postgresql' or parsed.hostname != '127.0.0.1'
            or parsed.username != 'postgres' or parsed.password is not None
            or parsed.path != '/cadence_integration_test' or not parsed.port
            or parsed.query or parsed.fragment):
        raise pytest.UsageError('Use only the explicit localhost disposable test database without credentials.')
    return url


def _external_service_disabled(*args, **kwargs):
    raise AssertionError('External services are disabled in tests; inject a mock.')


async def _async_external_service_disabled(*args, **kwargs):
    _external_service_disabled()


def pytest_configure(config):
    # Autouse fixtures run too late: importing app.api.main loads dotenv during
    # collection. Install these guards before importing any test modules.
    patches = pytest.MonkeyPatch()
    config._cadence_test_patches = patches
    patches.setattr('dotenv.load_dotenv', lambda *args, **kwargs: False)
    for name in (
        'TIGER_DATA_URL', 'TEST_TIGER_DATA_URL', 'TEST_CONVERSATION_DB_URL',
        'GROQ_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'ELEVENLABS_API_KEY',
        'CADENCE_ASR_ENABLED', 'CADENCE_ASR_SMOKE', 'CADENCE_MAX_QUESTIONS',
        'CADENCE_VOICE_ID', 'CADENCE_WHISPER_CACHE', 'CADENCE_WHISPER_MODEL',
        'PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD',
        'PGPASSFILE', 'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR',
        'PGSSLMODE', 'PGSSLKEY', 'PGSSLCERT', 'PGSSLROOTCERT',
    ):
        patches.delenv(name, raising=False)
    # libpq otherwise searches the user's default password/service files even
    # when tests supply a localhost URL. Never consult those private files.
    patches.setenv('PGPASSFILE', os.devnull)
    patches.setenv('PGSERVICEFILE', os.devnull)
    # Block SDK clients as well as HTTP transports, independent of which HTTP
    # library a provider version uses. Tests may inject their own fake clients.
    patches.setattr('groq.Groq', _external_service_disabled)
    patches.setattr('groq.AsyncGroq', _external_service_disabled)
    patches.setattr('google.genai.Client', _external_service_disabled)
    # In-process FastAPI TestClient and explicit mock transports remain usable.
    patches.setattr(httpx.HTTPTransport, 'handle_request', _external_service_disabled)
    patches.setattr(httpx.AsyncHTTPTransport, 'handle_async_request',
                    _async_external_service_disabled)
    disposable = config.getoption('--disposable-db-url')
    if disposable:
        disposable = _validate_disposable_database(disposable)
        connect = psycopg.connect

        def disposable_connect(conninfo='', **kwargs):
            # Fixtures can set their own search_path, but cannot redirect a
            # connection to another database or use inherited service config.
            if conninfo != disposable or set(kwargs) - {'row_factory', 'options', 'autocommit'}:
                return _external_service_disabled()
            return connect(conninfo, **kwargs)

        patches.setattr(psycopg, 'connect', disposable_connect)
        for name in ('TEST_TIGER_DATA_URL', 'TEST_CONVERSATION_DB_URL'):
            patches.setenv(name, disposable)
    else:
        patches.setattr(psycopg, 'connect', _external_service_disabled)


def pytest_unconfigure(config):
    patches = getattr(config, '_cadence_test_patches', None)
    if patches is not None:
        patches.undo()
