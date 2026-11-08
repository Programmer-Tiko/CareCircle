"""Regression checks for the suite's configuration and external-service guards."""
import asyncio

import dotenv
import httpx
import psycopg
import pytest


def test_dotenv_loading_is_disabled_before_application_import(monkeypatch):
    def unexpected_read(*args, **kwargs):
        raise AssertionError('Dotenv must not inspect private files.')

    monkeypatch.setattr('dotenv.main.DotEnv', unexpected_read)
    assert dotenv.load_dotenv('must-not-open.env') is False


def test_real_sync_http_requests_are_blocked():
    with httpx.Client() as client:
        with pytest.raises(AssertionError, match='External services are disabled'):
            client.get('https://example.invalid')


def test_real_async_http_requests_are_blocked():
    async def request():
        async with httpx.AsyncClient() as client:
            with pytest.raises(AssertionError, match='External services are disabled'):
                await client.get('https://example.invalid')

    asyncio.run(request())


def test_real_database_connections_are_blocked():
    with pytest.raises(AssertionError, match='External services are disabled'):
        psycopg.connect('')


@pytest.mark.parametrize('url', [
    'postgresql://postgres@remote.example:5432/cadence_integration_test',
    'postgresql://postgres:secret@127.0.0.1:5432/cadence_integration_test',
    'postgresql://postgres@127.0.0.1:5432/production',
    'postgresql://postgres@127.0.0.1:5432/cadence_integration_test?service=production',
])
def test_disposable_database_option_rejects_other_connections(url):
    from conftest import _validate_disposable_database
    with pytest.raises(pytest.UsageError):
        _validate_disposable_database(url)


@pytest.mark.parametrize('provider', ['groq', 'async_groq', 'gemini'])
def test_real_provider_clients_are_blocked(provider):
    from google import genai
    from groq import AsyncGroq, Groq

    factory = {'groq': Groq, 'async_groq': AsyncGroq, 'gemini': genai.Client}[provider]
    with pytest.raises(AssertionError, match='External services are disabled'):
        factory(api_key='test-only-key')
