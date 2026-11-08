"""Keep collection and tests independent of private configuration and services."""
import httpx
import psycopg
import pytest


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
    ):
        patches.delenv(name, raising=False)
    # Block SDK clients as well as HTTP transports, independent of which HTTP
    # library a provider version uses. Tests may inject their own fake clients.
    patches.setattr('groq.Groq', _external_service_disabled)
    patches.setattr('groq.AsyncGroq', _external_service_disabled)
    patches.setattr('google.genai.Client', _external_service_disabled)
    # In-process FastAPI TestClient and explicit mock transports remain usable.
    patches.setattr(httpx.HTTPTransport, 'handle_request', _external_service_disabled)
    patches.setattr(httpx.AsyncHTTPTransport, 'handle_async_request',
                    _async_external_service_disabled)
    patches.setattr(psycopg, 'connect', _external_service_disabled)


def pytest_unconfigure(config):
    patches = getattr(config, '_cadence_test_patches', None)
    if patches is not None:
        patches.undo()
