"""Headless, explicit fixture microphone + injected ASR/TTS. Never a physical-mic claim."""
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import httpx
import numpy as np
import pytest
import soundfile as sf

from test_browser_workflow import local_server
from test_conversations import conversation_clients
from app.api import speech
from app.audio.phrase_alignment import TranscriptionResult, WordTimestamp


@contextmanager
def voice_page(request, factory, monkeypatch, *, fallback=False):
    if not request.config.getoption('--browser-smoke'):
        pytest.skip('Enable --browser-smoke and a disposable database.')
    pw_api = pytest.importorskip('playwright.sync_api')
    executable = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    if not executable.is_file():
        pytest.skip('Chrome unavailable for optional browser verification.')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'fake-voice-test-key')
    requests = []
    audio = BytesIO()
    sf.write(audio, .02 * np.sin(np.arange(32000) * .1), 16000, format='WAV')

    def provider(url, **kwargs):
        requests.append(kwargs['json']['text'])
        if fallback:
            raise httpx.TimeoutException('injected failure')
        return httpx.Response(200, content=audio.getvalue(), headers={'Content-Type': 'audio/mpeg'}, request=httpx.Request('POST', url))

    monkeypatch.setattr('app.api.main.httpx.post', provider)
    with factory() as client, local_server(client.app) as base, pw_api.sync_playwright() as pw:
        client.app.dependency_overrides[speech.get_transcriber] = lambda: lambda path: TranscriptionResult(
            [WordTimestamp('People ask me to repeat myself', 0, 1, .75)], .75, 'mock-local-ASR')
        browser = pw.chromium.launch(executable_path=str(executable), headless=True, args=[
            '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
            '--use-file-for-fake-audio-capture=' + str(Path(__file__).parent / 'fixtures/speech_chunk.wav'),
            '--disable-background-networking', '--disable-component-update', '--disable-sync'])
        try:
            context = browser.new_context(permissions=['microphone'])

            def route_request(route):
                if not route.request.url.startswith(base + '/'):
                    route.abort()
                elif route.request.url.endswith('/capabilities'):
                    response = route.fetch()
                    payload = response.json()
                    payload.update(asr_enabled=True, asr_provider='injected-test-ASR')
                    route.fulfill(response=response, json=payload)
                else:
                    route.continue_()

            context.route('**/*', route_request)
            if fallback:
                context.add_init_script("""(() => {
                  window.__browserSpeech = [];
                  window.SpeechSynthesisUtterance = class { constructor(text) { this.text=text; } };
                  Object.defineProperty(window, 'speechSynthesis', {value:{
                    getVoices:()=>[{name:'Microsoft Zira test voice',voiceURI:'test-zira',lang:'en-US',localService:true}],
                    speak(u){window.__browserSpeech.push(u.text);setTimeout(()=>{u.onstart?.();u.onend?.();},30);},
                    cancel(){},pause(){},resume(){}
                  }});
                })();""")
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_default_timeout(20000)
            page.goto(base)
            pw_api.expect(page.locator('#freshProfileBtn')).to_be_enabled()
            page.locator('#connectionSettings').evaluate('(el) => el.open = true')
            page.locator('#profileId').fill('demo')
            with page.expect_response(lambda response: response.url == base + '/profiles/demo') as loaded_profile:
                page.locator('#connectBtn').click()
            assert loaded_profile.value.status == 200
            pw_api.expect(page.locator('#profileStatus')).to_contain_text('Reference ready', timeout=15000)
            page.locator('#historyBtn').click()
            page.get_by_role('button', name='Open question', exact=True).click()
            yield page, requests, client, errors, pw_api.expect
        finally:
            browser.close()


def test_voice_review_cancel_edit_send_confirm_and_recover(request, conversation_clients, monkeypatch):
    factory, _ = conversation_clients
    with voice_page(request, factory, monkeypatch) as (page, calls, client, errors, expect):
        expect(page.locator('#voiceStatus')).to_contain_text('speaking')
        first_question = page.locator('#questionText').inner_text()
        assert calls == [first_question]
        page.locator('#pauseSpeechBtn').click()
        expect(page.locator('#voiceStatus')).to_contain_text('paused')
        page.locator('#stopSpeechBtn').click()
        expect(page.locator('#recordAnswerBtn')).to_be_enabled()
        page.locator('#speakQuestionBtn').click()
        expect(page.locator('#voiceStatus')).to_contain_text('speaking')
        page.locator('#stopSpeechBtn').click()
        assert calls == [first_question], 'Replay must reuse this page\'s audio cache.'
        page.reload()
        expect(page.locator('#questionText')).to_have_text(first_question)
        expect(page.locator('#recordAnswerBtn')).to_be_enabled()
        assert calls == [first_question], 'An unanswered question cannot replay automatically on reload.'
        page.locator('#voiceEnabled').uncheck()

        # Cancel discards capture and cannot submit or overwrite a typed draft.
        page.locator('#answerText').fill('Fictional draft')
        page.locator('#recordAnswerBtn').click()
        expect(page.locator('#cancelAnswerBtn')).to_be_visible()
        page.locator('#cancelAnswerBtn').click()
        expect(page.locator('#recordAnswerBtn')).to_be_enabled()
        expect(page.locator('#answerText')).to_have_value('Fictional draft')

        # Fake microphone goes through actual MediaRecorder/WAV/HTTP; ASR is injected.
        page.locator('#recordAnswerBtn').click()
        page.wait_for_timeout(1400)
        if page.locator('#stopAnswerBtn').is_enabled():
            page.locator('#stopAnswerBtn').click()
        expect(page.locator('#transcriptLabel')).to_contain_text('what I heard')
        expect(page.locator('#answerText')).to_have_value('People ask me to repeat myself')
        expect(page.locator('#answerPreview')).to_be_visible()
        with factory.connect() as db:
            assert db.execute('SELECT count(*) AS n FROM conversation_turns WHERE answered_at IS NOT NULL').fetchone()['n'] == 0
            assert db.execute('SELECT count(*) AS n FROM checkins').fetchone()['n'] == 1
            baseline = db.execute("SELECT baseline_median FROM profiles WHERE profile_id='demo'").fetchone()['baseline_median']
            assert baseline['speaking_rate'] == 3.0, 'Conversational audio cannot replace the passage reference.'
        edited = 'Fictional test: people ask me to repeat myself at dinner.'
        page.locator('#answerText').fill(edited)
        page.locator('#answerBtn').click()
        expect(page.locator('#turnHistory')).to_contain_text(edited)
        expect(page.locator('#answerText')).to_have_value('')
        assert page.locator('#questionText').inner_text() != first_question
        page.locator('#finishConversationBtn').click()
        expect(page.locator('#confirmBtn')).to_be_enabled()
        expect(page.locator('#noteStatus')).to_contain_text('Not yet confirmed')
        page.locator('#correctionText').fill('Fictional correction for verification.')
        page.locator('#correctionBtn').click()
        expect(page.locator('#notePanel')).to_contain_text('Fictional correction')
        page.locator('#confirmBtn').click()
        expect(page.locator('#statusMessage')).to_contain_text('confirmed and saved')
        call_count = len(calls)
        page.reload()
        expect(page.locator('#notePanel')).to_contain_text('Fictional correction')
        assert len(calls) == call_count, 'Reload cannot speak a question or patient note automatically.'
        page.locator('#historyBtn').click()
        expect(page.locator('#historyList')).to_contain_text('Note confirmed')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert errors == []


def test_provider_fallback_permission_denial_and_typing(request, conversation_clients, monkeypatch):
    factory, _ = conversation_clients
    with voice_page(request, factory, monkeypatch, fallback=True) as (page, calls, client, errors, expect):
        expect(page.locator('#voiceStatus')).to_contain_text('Browser voice fallback')
        assert page.evaluate('window.__browserSpeech[0]') == page.locator('#questionText').inner_text()
        page.evaluate("() => { navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('injected denial','NotAllowedError')}; }")
        page.locator('#recordAnswerBtn').click()
        expect(page.locator('#errorMessage')).to_contain_text('permission was denied')
        page.locator('#answerText').fill('Fictional typed answer remains available.')
        page.locator('#answerBtn').click()
        expect(page.locator('#turnHistory')).to_contain_text('Fictional typed answer')
        assert errors == []


def test_autoplay_block_and_asr_failure_preserve_typing(request, conversation_clients, monkeypatch):
    from fastapi import HTTPException
    factory, _ = conversation_clients
    with voice_page(request, factory, monkeypatch) as (page, calls, client, errors, expect):
        page.locator('#stopSpeechBtn').click()
        page.evaluate("() => { HTMLMediaElement.prototype.play=()=>Promise.reject(new DOMException('test autoplay block','NotAllowedError')); }")
        page.locator('#speakQuestionBtn').click()
        expect(page.locator('#voiceStatus')).to_contain_text('permission')
        expect(page.locator('#recordAnswerBtn')).to_be_enabled()

        def unavailable(path):
            raise HTTPException(503, 'Local transcription temporarily unavailable.')
        client.app.dependency_overrides[speech.get_transcriber] = lambda: unavailable
        page.locator('#answerText').fill('Fictional draft retained after failure.')
        page.locator('#recordAnswerBtn').click()
        page.wait_for_timeout(700)
        if page.locator('#stopAnswerBtn').is_enabled():
            page.locator('#stopAnswerBtn').click()
        expect(page.locator('#errorMessage')).to_contain_text('temporarily unavailable')
        expect(page.locator('#answerText')).to_have_value('Fictional draft retained after failure.')
        expect(page.locator('#answerBtn')).to_be_enabled()
        with factory.connect() as db:
            assert db.execute('SELECT count(*) AS n FROM conversation_turns WHERE answered_at IS NOT NULL').fetchone()['n'] == 0
        assert errors == []
