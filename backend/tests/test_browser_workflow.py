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
from app.api import speech
from app.audio.phrase_alignment import TranscriptionResult, WordTimestamp


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
        client.app.dependency_overrides[speech.get_transcriber] = lambda: lambda path: TranscriptionResult(
            [WordTimestamp('People ask me to repeat myself', 0, 1, .8)], .8, 'injected-ASR')
        browser = pw.chromium.launch(executable_path=executable, headless=True, args=[
            '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
            '--use-file-for-fake-audio-capture=' + str(microphone),
            '--disable-background-networking', '--disable-component-update', '--disable-sync',
        ])
        try:
            context = browser.new_context(permissions=['microphone'])
            context.add_init_script("localStorage.setItem('cadence.voice.enabled', 'false')")
            # Even optional font requests stay offline. Only this test server
            # can be reached from the page; no application endpoints are mocked.
            reject_next_reference = [True]
            def route_request(route):
                if not route.request.url.startswith(base + '/'):
                    route.abort()
                elif route.request.url.endswith('/capabilities'):
                    response = route.fetch()
                    payload = response.json()
                    payload.update(asr_enabled=True, asr_provider='injected-ASR')
                    route.fulfill(response=response, json=payload)
                elif '/reference/validate' in route.request.url and reject_next_reference[0]:
                    reject_next_reference[0] = False
                    route.fulfill(status=422, json={'detail': 'Injected rejected reference. Please retry.'})
                else:
                    route.continue_()
            context.route('**/*', route_request)
            page = context.new_page()
            page.set_default_timeout(20000)
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            page.goto(base)
            playwright.expect(page.locator('#freshProfileBtn')).to_be_enabled()
            page.locator('#freshProfileBtn').click()
            playwright.expect(page.locator('#profileStatus')).to_contain_text('New profile')
            profile = page.locator('#profileId').input_value()
            assert profile.startswith('judge-')
            playwright.expect(page.locator('#referenceProgress')).to_have_text('Reference 1 of 3')
            playwright.expect(page.locator('#welcomeHelp')).to_contain_text('No personal voice reference')
            page.locator('#experimentalToggle').uncheck()
            page.locator('#verifyPassageToggle').uncheck()  # Fixture is not the full standardized passage.
            # This acceptance test covers passage capture and persistence.
            # TTS/playback controls have separate deterministic voice tests.

            def record():
                playwright.expect(page.locator('#recordBtn')).to_be_enabled()
                page.locator('#recordBtn').click()
                playwright.expect(page.locator('#stopBtn')).to_be_enabled()
                page.wait_for_timeout(3200)
                if page.locator('#stopBtn').is_enabled():
                    page.locator('#stopBtn').click()

            record()
            playwright.expect(page.locator('#errorMessage')).to_contain_text('rejected reference')
            playwright.expect(page.locator('#takeList audio')).to_have_count(0)
            playwright.expect(page.locator('#referenceProgress')).to_have_text('Reference 1 of 3')
            for count in range(1, 4):
                record()
                playwright.expect(page.locator('#takeList audio')).to_have_count(count)
                playwright.expect(page.locator('#takeList')).to_contain_text('Completed and accepted')
                assert page.locator('#referenceMeter').get_attribute('value') == str(count)
            with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/enroll')) as enrollment:
                page.locator('#enrollBtn').click()
            assert enrollment.value.status == 200
            assert enrollment.value.json()['n_reference_takes'] == 3
            playwright.expect(page.locator('#profileStatus')).to_contain_text('Reference ready')
            playwright.expect(page.locator('#referenceProgress')).to_have_text('Baseline ready')

            with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/checkin')) as reading:
                record()
            assert reading.value.status == 200
            assert len(reading.value.json()['measured']['feature_scores']) == 4
            playwright.expect(page.locator('#measurementGrid')).to_contain_text('Personal reference:')
            playwright.expect(page.locator('#conversationPanel')).to_be_hidden()
            page.locator('#continueConversationBtn').click()
            playwright.expect(page.locator('#answerText')).to_be_enabled()
            for answer in ('People ask me to repeat myself', 'During dinner'):
                if answer == 'People ask me to repeat myself':
                    page.locator('#recordAnswerBtn').click()
                    page.wait_for_timeout(1500)
                    if page.locator('#stopAnswerBtn').is_enabled():
                        page.locator('#stopAnswerBtn').click()
                    playwright.expect(page.locator('#transcriptLabel')).to_contain_text('what I heard')
                    playwright.expect(page.locator('#answerText')).to_have_value(answer)
                    with factory.connect() as db:
                        assert db.execute('SELECT count(*) AS n FROM conversation_turns WHERE answered_at IS NOT NULL AND session_id IN (SELECT session_id FROM conversations WHERE profile_id=%s)', (profile,)).fetchone()['n'] == 0
                page.locator('#answerText').fill(answer)
                page.locator('#answerBtn').click()
                if answer == 'People ask me to repeat myself':
                    playwright.expect(page.locator('#answerText')).to_be_enabled()
            playwright.expect(page.locator('#confirmBtn')).to_be_enabled()
            page.locator('#correctionText').fill('Fictional correction: this happened yesterday.')
            page.locator('#correctionBtn').click()
            playwright.expect(page.locator('#notePanel')).to_contain_text('Fictional correction')
            page.locator('#confirmBtn').click()
            playwright.expect(page.locator('#statusMessage')).to_contain_text('confirmed and saved')
            page.reload()
            playwright.expect(page.locator('#notePanel')).to_contain_text('Fictional correction')
            playwright.expect(page.locator('#recordBtn')).to_be_enabled()
            page.locator('#experimentalToggle').uncheck()
            page.locator('#verifyPassageToggle').uncheck()  # Reload restores the normal live defaults.

            # Starting another reading must not silently confirm that draft.
            with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/checkin')) as second:
                record()
            assert second.value.status == 200
            page.locator('#continueConversationBtn').click()
            playwright.expect(page.locator('#answerText')).to_be_enabled()
            page.locator('#resetCheckinBtn').click()
            playwright.expect(page.locator('#statusMessage')).to_contain_text('unconfirmed draft')
            page.locator('#historyBtn').click()
            playwright.expect(page.locator('#historyList')).to_contain_text('Note confirmed')
            playwright.expect(page.locator('#historyList')).to_contain_text('Conversation: abstained')
            page.locator('#refreshHistoryBtn').click()
            playwright.expect(page.locator('#refreshHistoryBtn')).to_be_enabled()
            page.get_by_text('View saved measurements', exact=True).first.click()
            playwright.expect(page.locator('#historyList details').first).to_contain_text('Personal reference:')
            page.get_by_role('button', name='View note', exact=True).last.click()
            playwright.expect(page.locator('#noteStatus')).to_contain_text('Confirmed')
            playwright.expect(page.locator('#noteSaid')).to_contain_text('People ask me to repeat myself')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
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
        assert db.execute("SELECT baseline_median FROM profiles WHERE profile_id='demo'").fetchone()['baseline_median']['speaking_rate'] == 3.0
