"""Optional real Chrome UI -> HTTP -> VAD/RAG -> disposable SQL acceptance.

The microphone uses the licensed control-speech fixture, not a person's live
microphone. Provider selection is injected; no cloud calls or real profiles.
"""
from contextlib import contextmanager
from pathlib import Path
import shutil
import socket
from threading import Thread
import time
from urllib.parse import urlsplit
from uuid import uuid4

import numpy as np
import pytest
import soundfile as sf
import uvicorn

from test_conversations import conversation_clients, corpus_selector


@contextmanager
def local_server(app):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='error', access_log=False))
    worker = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        assert server.started, 'Disposable UI server did not start.'
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        listener.close()
        assert not worker.is_alive(), 'UI test server did not stop.'


def test_microphone_to_confirmed_history_and_unconfirmed_reset(request, conversation_clients, tmp_path):
    if not request.config.getoption('--browser-smoke'):
        pytest.skip('Enable --browser-smoke with the disposable test database and optional Playwright tooling.')
    playwright = pytest.importorskip('playwright.sync_api')
    candidates = [
        Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
        Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
    ]
    executable = next((str(p) for p in candidates if p.is_file()), None)
    executable = executable or shutil.which('google-chrome') or shutil.which('chromium')
    assert executable, 'Install Chrome/Chromium or Edge before requesting browser acceptance.'
    factory, _ = conversation_clients

    def selector(context):
        if len(context['turns']) >= 2:
            return {'decision': 'complete', 'resolved': True}
        return corpus_selector(context)

    audio, rate = sf.read(Path(__file__).parent / 'fixtures/speech_chunk.wav', dtype='float32')
    microphone = tmp_path / 'fictional-microphone.wav'
    sf.write(microphone, np.tile(np.concatenate([audio, np.zeros(round(rate * .2))]), 12), rate)
    profile = 'browser-' + uuid4().hex
    page_errors = []
    with factory(selector) as client, local_server(client.app) as base, playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable, headless=True, args=[
            '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
            '--use-file-for-fake-audio-capture=' + str(microphone),
            '--disable-background-networking', '--disable-component-update', '--disable-sync',
        ])
        try:
            context = browser.new_context(permissions=['microphone'])
            # Even optional font requests stay offline. Only this test server
            # can be reached from the page; no application endpoints are mocked.
            context.route('**/*', lambda route: route.continue_()
                          if route.request.url.startswith(base + '/') else route.abort())
            page = context.new_page()
            page.set_default_timeout(20000)
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            page.goto(base)
            playwright.expect(page.locator('#connectBtn')).to_be_enabled()
            page.locator('#profileId').fill(profile)
            page.locator('#connectBtn').click()
            playwright.expect(page.locator('#profileStatus')).to_contain_text(profile)
            page.locator('#experimentalToggle').uncheck()

            def record():
                playwright.expect(page.locator('#recordBtn')).to_be_enabled()
                page.locator('#recordBtn').click()
                playwright.expect(page.locator('#stopBtn')).to_be_enabled()
                page.wait_for_timeout(3200)
                if page.locator('#stopBtn').is_enabled():
                    page.locator('#stopBtn').click()

            for count in range(1, 4):
                record()
                playwright.expect(page.locator('#takeList audio')).to_have_count(count)
            with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/enroll')) as enrollment:
                page.locator('#enrollBtn').click()
            assert enrollment.value.status == 200
            playwright.expect(page.locator('#profileStatus')).to_contain_text('Reference ready')

            with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/checkin')) as reading:
                record()
            assert reading.value.status == 200
            assert len(reading.value.json()['measured']['feature_scores']) == 4
            playwright.expect(page.locator('#answerBtn')).to_be_enabled()
            for answer in ('People ask me to repeat myself', 'During dinner'):
                page.locator('#answerText').fill(answer)
                page.locator('#answerBtn').click()
                if answer == 'People ask me to repeat myself':
                    playwright.expect(page.locator('#answerBtn')).to_be_enabled()
            playwright.expect(page.locator('#confirmBtn')).to_be_enabled()
            page.locator('#correctionText').fill('Fictional correction: this happened yesterday.')
            page.locator('#correctionBtn').click()
            playwright.expect(page.locator('#notePanel')).to_contain_text('Fictional correction')
            page.locator('#confirmBtn').click()
            playwright.expect(page.locator('#statusMessage')).to_contain_text('confirmed and saved')
            page.reload()
            playwright.expect(page.locator('#notePanel')).to_contain_text('Fictional correction')
            playwright.expect(page.locator('#recordBtn')).to_be_enabled()

            # Starting another reading must not silently confirm that draft.
            with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/checkin')) as second:
                record()
            assert second.value.status == 200
            playwright.expect(page.locator('#answerBtn')).to_be_enabled()
            page.locator('#resetCheckinBtn').click()
            playwright.expect(page.locator('#statusMessage')).to_contain_text('unconfirmed draft')
            page.locator('#historyBtn').click()
            playwright.expect(page.locator('#historyList')).to_contain_text('Note confirmed')
            playwright.expect(page.locator('#historyList')).to_contain_text('Conversation: abstained')
            assert page_errors == []
        finally:
            browser.close()
    with factory.connect() as db:
        rows = db.execute('SELECT state, note, confirmed_at FROM conversations WHERE profile_id=%s '
                          'ORDER BY created_at', (profile,)).fetchall()
        assert [row['state'] for row in rows] == ['confirmed', 'abstained']
        assert rows[0]['confirmed_at'] and rows[0]['note']['patient_correction'].startswith('Fictional correction')
        assert rows[1]['confirmed_at'] is None
        assert rows[1]['note']['status'] == 'awaiting_confirmation'
