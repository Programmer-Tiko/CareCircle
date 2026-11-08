'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let busy = false, connected = null, enrolled = false, compatible = true, capabilities = {};
  let session = null, latestMeasured = null, latestCheckin = null, baselineMedian = {};
  let recording = null, checkinTake = null, answerTake = null, pendingAnswer = null;
  const voice = new window.CadenceVoice($('speechPlayer'), (state, label) => {
    $('voiceStatus').textContent = label;
    $('voiceStatus').dataset.state = state;
    $('pauseSpeechBtn').textContent = state === 'paused' ? 'Resume speaking' : 'Pause speaking';
    updateControls();
  });
  try { $('voiceEnabled').checked = localStorage.getItem('cadence.voice.enabled') !== 'false'; } catch { /* Preferences are optional. */ }
  function clearAnswer(clearText = true) {
    if (answerTake) URL.revokeObjectURL(answerTake.url);
    answerTake = null; $('answerPreview').pause(); $('answerPreview').removeAttribute('src'); $('answerPreview').load(); $('answerPreview').hidden = true;
    if (clearText) $('answerText').value = '';
    $('transcriptLabel').textContent = 'Your answer — speak or type';
    $('answerStatus').textContent = 'Tap to answer when Cadence finishes speaking.';
  }
  const references = [], retryAnswers = new Map();
  const featureLabels = {
    pause_fraction: ['Time in internal pauses', value => `${(value * 100).toFixed(1)}%`],
    longest_internal_gap: ['Longest internal pause', value => `${value.toFixed(2)} s`],
    speaking_rate: ['Passage rate estimate', value => `${value.toFixed(2)} syll/s`],
    mean_speech_segment_duration: ['Average speech burst', value => `${value.toFixed(2)} s`]
  };
  const stored = (() => { try { return JSON.parse(localStorage.getItem('cadence.connection') || '{}'); } catch { return {}; } })();
  const defaultBase = location.protocol === 'file:' ? 'http://localhost:8000' : location.origin;
  $('apiBase').value = stored.base || defaultBase;
  $('profileId').value = stored.profile || 'demo-' + new Date().toISOString().slice(0, 10);
  function message(text) { $('statusMessage').textContent = text; }
  function error(text) { $('errorMessage').textContent = text; $('errorMessage').hidden = !text; }
  function saveConnection() {
    if (!connected) return;
    try { localStorage.setItem('cadence.connection', JSON.stringify({ ...connected, session: session?.session_id || null })); } catch { /* Storage may be unavailable in private mode. */ }
  }
  function pending() { return session && session.state !== 'confirmed'; }
  function updateControls() {
    const locked = busy || Boolean(recording);
    const hasPending = Boolean(pending());
    const configured = connected && $('profileId').value.trim() === connected.profile && $('apiBase').value.trim().replace(/\/$/, '') === connected.base;
    for (const id of ['apiBase', 'profileId', 'connectBtn', 'newProfileBtn', 'freshProfileBtn']) $(id).disabled = locked || hasPending;
    $('captureKind').disabled = locked || hasPending;
    $('recordBtn').disabled = locked || voice.active || !configured || !compatible || hasPending || Boolean(latestCheckin && !session) || ($('captureKind').value === 'reference' && references.length >= 5);
    // A pending (unconfirmed) conversation from an earlier check-in is the
    // only thing that blocks recordBtn above -- give an explicit, visible
    // way out of that instead of leaving the patient staring at a disabled
    // button with no clear next step.
    $('resetCheckinBtn').hidden = !hasPending; $('resetCheckinHelp').hidden = !hasPending;
    $('resetCheckinBtn').disabled = locked;
    $('stopBtn').disabled = !recording || recording.kind === 'answer' || busy;
    $('stopAnswerBtn').disabled = !recording || recording.kind !== 'answer' || busy;
    $('enrollBtn').hidden = enrolled;
    $('enrollBtn').disabled = locked || !configured || enrolled || references.length < 3 || hasPending;
    $('uploadBtn').hidden = !enrolled;
    $('uploadBtn').disabled = locked || !configured || !enrolled || !compatible || !checkinTake || hasPending;
    $('experimentalToggle').disabled = locked || hasPending;
    $('verifyPassageToggle').disabled = locked || hasPending;
    const turn = session?.turns?.find(item => !item.answered_at && !item.closed_at);
    $('answerBtn').disabled = locked || voice.active || session?.state !== 'active' || !turn || !$('answerText').value.trim();
    $('finishConversationBtn').disabled = locked || session?.state !== 'active';
    $('answerText').disabled = locked || session?.state !== 'active';
    $('recordAnswerBtn').disabled = locked || voice.active || !capabilities.asr_enabled || session?.state !== 'active' || !turn;
    $('recordAnswerBtn').hidden = false;
    $('recordAnswerBtn').textContent = recording?.kind === 'answer' ? 'Listening to you…' : answerTake ? 'Record again' : 'Tap to answer';
    $('recordAnswerBtn').setAttribute('aria-pressed', String(recording?.kind === 'answer'));
    $('typeAnswerBtn').textContent = answerTake ? 'Edit transcript' : 'Switch to typing';
    $('cancelAnswerBtn').hidden = !(recording?.kind === 'answer' || pendingAnswer);
    $('skipQuestionBtn').disabled = locked || voice.active || session?.state !== 'active' || !turn;
    $('typeAnswerBtn').disabled = locked;
    $('pauseSpeechBtn').disabled = !['speaking', 'paused'].includes(voice.state);
    $('stopSpeechBtn').disabled = !voice.active;
    $('asrHelp').hidden = false;
    $('asrHelp').textContent = capabilities.asr_enabled ? 'Local speech recognition can make mistakes. Review or edit every transcript, then choose Confirm and send. A quiet room helps.' : 'Local answer transcription is unavailable on this service. Switch to typing to continue; no transcript will be fabricated.';
    $('stopAnswerBtn').hidden = !recording || recording.kind !== 'answer';
    $('confirmBtn').disabled = locked || !session || !['complete', 'abstained'].includes(session.state);
    $('confirmBtn').hidden = session?.state === 'confirmed';
    $('correctionBtn').disabled = locked || !session || !['complete', 'abstained'].includes(session.state);
    $('correctionText').disabled = locked;
    $('saveRoutineNoteBtn').disabled = locked || !configured || !enrolled;
    $('routineNoteText').disabled = locked;
    $('refreshHistoryBtn').disabled = locked || !connected;
    $('speakQuestionBtn').disabled = locked || !turn;
    $('speakNoteBtn').disabled = locked;
    $('speakQuestionBtn').hidden = false;
    $('speakNoteBtn').hidden = false;
    $('continueConversationBtn').hidden = !latestCheckin || Boolean(session);
    $('continueConversationBtn').disabled = locked || !configured || !latestCheckin || Boolean(session);
    document.querySelectorAll('[data-remove], [data-open-session]').forEach(button => { button.disabled = locked; });
    renderProgress();
  }
  function renderProgress() {
    const count = references.filter(take => take.accepted).length;
    $('referenceMeter').value = enrolled ? 3 : Math.min(count, 3);
    $('referenceProgress').textContent = enrolled ? 'Baseline ready' : count >= 3 ? `${count} references accepted. Save my reference to create your baseline.` : `Reference ${count + 1} of 3`;
    $('referenceStorage').textContent = enrolled ? 'Your personal acoustic baseline is saved in the database. Record today\u2019s reading below.' : `${count} accepted of 3 required${references.some(take => !take.accepted) ? '; older server recordings await validation on Save' : ''}. Recordings are held in this tab; Save my reference rechecks them and persists the baseline. Closing or reconnecting before saving loses these takes.`;
    $('welcomeHeading').textContent = !enrolled ? 'Welcome to Cadence' : session?.state === 'confirmed' ? 'Your check-in is saved' : 'Your personal reference is ready';
    $('welcomeHelp').textContent = !enrolled ? 'No personal voice reference exists yet. Three comfortable readings help Cadence compare your future readings with your own usual speech. Read the full passage each time.' : latestMeasured ? 'Review the actual measurements, then put them in context through a conversation. You decide when your report is confirmed.' : 'Next, read the same passage once for today\u2019s check-in. Cadence compares it with your saved personal reference.';
    const stage = !enrolled ? 'reference' : session ? (session.state === 'active' ? 'conversation' : 'report') : latestCheckin ? 'measurement' : 'checkin';
    document.querySelectorAll('#journeyProgress [data-stage]').forEach(item => {
      if (item.dataset.stage === stage) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');
    });
  }
  async function task(operation) {
    if (busy || recording) return;
    busy = true; error(''); updateControls();
    try { await operation(); } catch (problem) { if (problem.name !== 'AbortError') error(problem.message || 'The request could not be completed.'); }
    finally { busy = false; updateControls(); }
  }
  function target() {
    const base = new URL($('apiBase').value.trim());
    if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) throw new Error('Enter an HTTP(S) API address without credentials, query, or fragment.');
    const profile = $('profileId').value.trim();
    if (!profile) throw new Error('Choose a fictional profile ID first.');
    return { base: base.href.replace(/\/$/, ''), profile };
  }
  function profilePath(binding, suffix = '') { return '/profiles/' + encodeURIComponent(binding.profile) + suffix; }
  function sessionPath(binding = connected, active = session) { return profilePath(binding, '/conversations/' + encodeURIComponent(active.session_id)); }
  async function request(binding, path, { method = 'GET', body, audio = false, allow404 = false, signal = null, timeoutMs = 180000 } = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) controller.abort();
    const timeout = setTimeout(abort, timeoutMs);
    try {
      const options = { method, signal: controller.signal };
      if (body instanceof FormData) options.body = body;
      else if (body !== undefined) { options.headers = { 'Content-Type': 'application/json' }; options.body = JSON.stringify(body); }
      const response = await fetch(binding.base + path, options);
      if (audio && response.ok) return await response.blob();
      const text = await response.text();
      let data; try { data = JSON.parse(text); } catch { data = {}; }
      $('apiResponse').textContent = `${method} ${path}\nHTTP ${response.status}\n${JSON.stringify(data, null, 2)}`;
      if (allow404 && response.status === 404) return null;
      if (!response.ok) {
        const detail = typeof data.detail === 'string' ? data.detail
          : typeof data.detail?.message === 'string' ? data.detail.message
          : Array.isArray(data.detail) ? data.detail.map(item => `${(item.loc || []).join('.')}: ${item.msg}`).join('; ')
          : `Request returned HTTP ${response.status}.`;
        const problem = new Error(detail); problem.status = response.status; throw problem;
      }
      return data;
    } catch (problem) {
      if (problem.name === 'AbortError') { if (signal?.aborted) throw problem; throw new Error('The service took too long to respond. Your typed answer is still here; retry when ready.'); }
      if (problem instanceof TypeError) throw new Error('Cannot reach the API. Check the address and that the backend is running.');
      throw problem;
    } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
  }
  function clearTakes() {
    for (const take of references) URL.revokeObjectURL(take.url);
    references.length = 0;
    if (checkinTake) URL.revokeObjectURL(checkinTake.url);
    checkinTake = null; renderTakes();
  }
  async function connect() {
    const binding = target();
    message('Checking the service and your profile…');
    const caps = await request(binding, '/capabilities');
    $('connectionMode').textContent = caps.question_selection === 'offline-demo'
      ? 'Offline question demo: guidance, safety and storage are real; model selection is simulated. Answers are not sent to Groq.'
      : caps.question_selection === 'unavailable'
      ? 'Live question selection is not configured. Measurements and notes work, but a supported question may be unavailable.'
      : 'Live question selection uses Groq with the existing evidence guidance. Only confirmed answer text is sent.';
    const profile = await request(binding, profilePath(binding), { allow404: true });
    voice.clear(); clearAnswer(); clearTakes();
    connected = Object.freeze(binding); capabilities = caps;
    $('verifyPassageLabel').hidden = !caps.asr_enabled; enrolled = Boolean(profile); compatible = profile?.baseline_compatible !== false && (!profile || profile.condition === 'parkinsons');
    session = null; latestMeasured = null; latestCheckin = null; baselineMedian = profile?.baseline_median || {};
    $('measurementPanel').hidden = true; $('conversationPanel').hidden = true; $('notePanel').hidden = true;
    $('routineNotePanel').hidden = !enrolled;
    $('passageText').textContent = caps.passage?.text || 'Passage unavailable; reconnect before recording.';
    $('passageMeta').textContent = caps.passage ? `${caps.passage.syllable_count} fixed syllables · use this exact passage for reference and check-in` : '';
    $('profileStatus').textContent = enrolled ? (compatible ? 'Reference ready' : 'Older reference · new profile needed') : 'New profile · no reference yet';
    $('captureHeading').textContent = enrolled ? 'Your daily reading' : 'Get to know your usual';
    $('captureHelp').textContent = enrolled ? 'Read at your comfortable pace. We compare with your own reference.' : 'Record 3–5 comfortable readings to make your personal reference.';
    $('captureKind').value = enrolled ? 'checkin' : 'reference';
    if (profile && !compatible) error('This profile uses a legacy condition or reference protocol. Choose a new profile ID for the Parkinson’s self-check. Existing history is preserved.');
    if (stored.base === binding.base && stored.profile === binding.profile && stored.session) {
      const restored = await request(binding, profilePath(binding, '/conversations/' + encodeURIComponent(stored.session)), { allow404: true });
      if (restored) renderSession(restored, { autoplay: false });
    }
    saveConnection();
    $('connectionSettings').open = !compatible;
    message(enrolled ? 'Connected. Your reference is ready.' : 'Connected. Record at least three reference readings to begin.');
    if (session?.state === 'active') message('Your unfinished conversation is restored. Continue with the question below.');
    await refreshHistory();
  }
  function encodeWav(buffer) {
    const size = 44 + buffer.length * 2;
    if (!buffer.length || size > 20 * 1024 * 1024) throw new Error('Recording is empty or exceeds the 20 MiB WAV limit. Try a shorter recording.');
    const output = new ArrayBuffer(size), view = new DataView(output);
    const text = (offset, value) => [...value].forEach((letter, i) => view.setUint8(offset + i, letter.charCodeAt(0)));
    text(0, 'RIFF'); view.setUint32(4, size - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, buffer.sampleRate, true); view.setUint32(28, buffer.sampleRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, size - 44, true);
    const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
    for (let i = 0; i < buffer.length; i++) {
      let value = 0; for (const channel of channels) value += channel[i] / channels.length;
      value = Math.max(-1, Math.min(1, value)); view.setInt16(44 + i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
    }
    return new Blob([output], { type: 'audio/wav' });
  }
  async function startRecording(kind) {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Microphone recording needs a supported browser on localhost or HTTPS.');
    const binding = connected;
    if (!binding) throw new Error('Connect a profile first.');
    if (voice.active) throw new Error('Stop Cadence speaking before recording.');
    document.querySelectorAll('audio').forEach(player => player.pause());
    let stream, context;
    try {
      context = new (window.AudioContext || window.webkitAudioContext)(); await context.resume();
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
      const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(value => MediaRecorder.isTypeSupported(value));
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      const capture = { kind, binding, context, stream, recorder, chunks: [], activeSession: session, failed: false, started: Date.now() };
      recorder.ondataavailable = event => { if (event.data.size) capture.chunks.push(event.data); };
      recorder.onerror = event => { capture.failed = true; error(event.error?.message || 'Recording failed. Please try again.'); if (recorder.state !== 'inactive') recorder.stop(); };
      recorder.onstop = () => finishRecording(capture).then(() => {
        // The check-in reading itself should feel like one continuous
        // interaction, not record-then-remember-to-press-another-button --
        // submit it the moment it's ready. Reference/enrollment takes still
        // need an explicit Save after collecting 3-5 of them, so this only
        // applies to a single check-in recording.
        if (capture.kind === 'checkin' && !capture.failed && !capture.cancelled && checkinTake) task(submitCheckin);
        // Conversational transcripts always wait for explicit patient review and submission.
      });
      recording = capture;
      if (kind === 'answer') { pendingAnswer = capture; $('answerStatus').textContent = 'Listening to you…'; }
      recorder.start(500);
      capture.limit = setTimeout(() => stopRecording(), 60000);
      capture.timer = setInterval(() => { $(kind === 'answer' ? 'answerRecordingTimer' : 'recordingTimer').textContent = `${Math.floor((Date.now() - capture.started) / 1000)}s · recording`; }, 1000);
      watchForSilence(capture);
      message(kind === 'answer' ? 'Recording your answer. It will stop automatically once you finish speaking, or choose Finish answer recording.' : 'Recording. Read the passage; it will stop automatically once you finish, or choose Finish recording.');
    } catch (problem) {
      stream?.getTracks().forEach(track => track.stop()); if (context) await context.close();
      if (problem.name === 'NotAllowedError') throw new Error('Microphone permission was denied. Allow microphone access in your browser, then try again.');
      if (problem.name === 'NotFoundError') throw new Error('No microphone was found. Connect one and try again.');
      throw problem;
    }
  }
  function stopRecording() {
    if (!recording || recording.recorder.state === 'inactive') return;
    busy = true; updateControls(); recording.recorder.stop();
  }
  // Natural turn-taking instead of a manual Stop press: watch real mic
  // volume while recording and end the turn automatically once speech has
  // clearly started and then clearly stopped. Heuristic (RMS over a
  // rolling window, not a trained VAD) -- it needs a genuinely quiet room
  // to behave well, and the manual Stop button and the 60s hard limit both
  // stay as fallbacks if it misreads a noisy environment.
  function watchForSilence(capture) {
    const SPEECH_RMS = 0.02, SILENCE_RMS = 0.012, SILENCE_HOLD_MS = 1500, MIN_SPEECH_MS = 400;
    const analyser = capture.context.createAnalyser(); analyser.fftSize = 2048;
    capture.context.createMediaStreamSource(capture.stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    let speechStartedAt = null, silenceStartedAt = null;
    capture.silenceWatch = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      let sumSquares = 0; for (const sample of samples) sumSquares += sample * sample;
      const rms = Math.sqrt(sumSquares / samples.length);
      const now = Date.now();
      // Show input activity in patient language; keep numeric RMS thresholds
      // out of the presentation flow. This indicator never accepts a take.
      const report = (label) => { $('silenceDebug').textContent = label.startsWith('quiet') ? 'Pause detected' : label === 'waiting for speech' ? 'Listening for your voice' : 'Voice detected'; };
      if (rms >= SPEECH_RMS) { speechStartedAt ??= now; silenceStartedAt = null; report('speaking'); return; }
      if (!speechStartedAt || now - speechStartedAt < MIN_SPEECH_MS) { report('waiting for speech'); return; }
      if (rms >= SILENCE_RMS) { silenceStartedAt = null; report('speaking (quiet)'); return; }
      silenceStartedAt ??= now;
      const quietFor = ((now - silenceStartedAt) / 1000).toFixed(1);
      report(`quiet ${quietFor}s / ${SILENCE_HOLD_MS / 1000}s`);
      if (now - silenceStartedAt >= SILENCE_HOLD_MS) stopRecording();
    }, 100);
  }
  async function finishRecording(capture) {
    clearTimeout(capture.limit); clearInterval(capture.timer); clearInterval(capture.silenceWatch);
    $('silenceDebug').textContent = '';
    capture.stream.getTracks().forEach(track => track.stop());
    recording = null; busy = true; updateControls(); $('recordingTimer').textContent = ''; $('answerRecordingTimer').textContent = '';
    try {
      if (capture.failed || capture.cancelled) return;
      message('Preparing your WAV recording…');
      const buffer = await capture.context.decodeAudioData(await new Blob(capture.chunks, { type: capture.recorder.mimeType }).arrayBuffer());
      const blob = encodeWav(buffer);
      if (capture.kind === 'answer') {
        if (session?.session_id !== capture.activeSession?.session_id) throw new Error('The conversation changed; record the answer again.');
        $('answerStatus').textContent = 'Transcribing locally…'; message('Transcribing your answer for review…');
        capture.controller = new AbortController();
        const form = new FormData(); form.append('file', blob, 'answer.wav');
        const result = await request(capture.binding, '/transcribe', { method: 'POST', body: form, signal: capture.controller.signal });
        if (capture.cancelled || session?.session_id !== capture.activeSession?.session_id) return;
        if (!result.text?.trim()) throw new Error('No words were transcribed. You can type your answer or record again.');
        clearAnswer(); answerTake = { blob, url: URL.createObjectURL(blob) };
        $('answerPreview').src = answerTake.url; $('answerPreview').hidden = false;
        $('transcriptLabel').textContent = 'Here’s what I heard:';
        $('answerStatus').textContent = 'Review and edit these words. Nothing has been sent to the conversation yet.';
        $('answerText').value = result.text.trim();
        message('Transcript ready. Review or edit it, then choose Confirm and send.'); $('answerText').focus();
      } else {
        let accepted = false;
        if (capture.kind === 'reference' && capabilities.reference_validation) {
          message(`Checking reference ${references.length + 1} through the acoustic pipeline\u2026`);
          const form = new FormData(); form.append('file', blob, 'reference.wav');
          const suffix = capabilities.asr_enabled && $('verifyPassageToggle').checked ? '?verify_passage=true' : '';
          const result = await request(capture.binding, '/reference/validate' + suffix, { method: 'POST', body: form });
          if (result.status !== 'accepted') throw new Error('Reference was not accepted. Please retry this reading.');
          accepted = true;
        }
        const take = { blob, seconds: buffer.duration, url: URL.createObjectURL(blob), accepted };
        if (capture.kind === 'reference') references.push(take);
        else { if (checkinTake) URL.revokeObjectURL(checkinTake.url); checkinTake = take; }
        renderTakes(); message(capture.kind === 'reference' ? accepted ? `Reference ${references.length} completed and accepted. ${references.length >= 3 ? 'Choose Save my reference.' : 'Record the next full reading.'}` : 'Reference recorded. This older service will validate all takes when you save.' : 'Your check-in recording is ready to compare.');
      }
    } catch (problem) { capture.failed = true; if (!capture.cancelled) { error(problem.message || 'Could not decode this recording. Try another supported browser.'); if (capture.kind === 'answer') $('answerStatus').textContent = 'Transcription did not finish. Record again, or type your answer.'; } }
    finally { if (pendingAnswer === capture) pendingAnswer = null; await capture.context.close(); busy = false; updateControls(); }
  }
  function renderTakes() {
    $('takeList').replaceChildren();
    [...references.map((take, i) => [take, `Reference ${i + 1}`]), ...(checkinTake ? [[checkinTake, 'Today’s reading']] : [])].forEach(([take, title]) => {
      const row = document.createElement('div'); row.className = 'take-row';
      const label = document.createElement('p'); label.textContent = `${title} · ${take.seconds.toFixed(1)} seconds${references.includes(take) ? take.accepted ? ' · Completed and accepted' : ' · Recorded; awaiting validation on Save' : ''}`;
      const remove = document.createElement('button'); remove.className = 'text-button'; remove.textContent = 'Remove'; remove.dataset.remove = '';
      remove.setAttribute('aria-label', 'Remove ' + title); remove.onclick = () => { if (busy || recording) return; URL.revokeObjectURL(take.url); if (take === checkinTake) checkinTake = null; else references.splice(references.indexOf(take), 1); renderTakes(); updateControls(); };
      const audio = document.createElement('audio'); audio.controls = true; audio.src = take.url; audio.setAttribute('aria-label', 'Preview ' + title);
      row.append(label, remove, audio); $('takeList').append(row);
    });
  }
  function metric(container, label, value, score) {
    const card = document.createElement('div'); card.className = 'metric';
    const number = document.createElement('div'); number.className = 'value'; number.textContent = value;
    const title = document.createElement('div'); title.className = 'label'; title.textContent = label;
    card.append(number, title);
    // Uncalibrated z-scores stay in the explicit API response details.
    container.append(card);
  }
  function renderMeasured(measured) {
    if (!measured) return;
    latestMeasured = measured; $('measurementPanel').hidden = false; $('measurementGrid').replaceChildren();
    for (const [key, [label, format]] of Object.entries(featureLabels)) {
      const value = measured.features?.[key]; metric($('measurementGrid'), label, Number.isFinite(value) ? format(value) : 'Unavailable', measured.feature_scores?.[key]);
      const reference = (measured.reference_median || baselineMedian)[key];
      const card = $('measurementGrid').lastElementChild;
      if (Number.isFinite(reference) && Number.isFinite(value)) {
        paragraph(card, 'Personal reference: ' + format(reference), 'small muted');
        paragraph(card, 'Difference: ' + (value - reference >= 0 ? '+' : '\u2212') + format(Math.abs(value - reference)), 'small muted');
      } else paragraph(card, 'Personal reference unavailable for this historical reading.', 'small muted');
    }
    const status = measured.deviation_from_baseline;
    $('outcomeText').textContent = status === 'persistent' ? 'The timing persistence threshold was met. A question can help put this reading in context.' : status === 'elevated' ? 'This reading differs from your reference; the repeated-change threshold was not met.' : status === 'usual' ? 'The repeated-change threshold was not met. This describes the recording, not your health.' : 'The recording classification is unavailable. No conclusion about your health can be drawn.';
    const phrase = measured.phrase_evidence;
    const placed = phrase?.pause_events?.filter(event => event.provenance === 'measured') || [];
    $('phraseStatus').textContent = phrase?.status === 'available'
      ? `Passage transcript: ${phrase.phrase_match}.${phrase.alignment_available ? ' Estimated word-level pauses: ' + placed.filter(event => event.category === 'within_clause').length + ' within clauses; ' + placed.filter(event => event.category === 'punctuation_adjacent').length + ' at punctuation; ' + placed.filter(event => event.category !== 'within_clause' && event.category !== 'punctuation_adjacent').length + ' unclassified.' : ' Word-level timing is unavailable.'} This does not verify every recording condition.`
      : 'Passage was not automatically verified for this recording.';
    const evidence = measured.waveform_evidence;
    $('experimentalPanel').hidden = !evidence;
    $('experimentalValues').replaceChildren();
    if (evidence) {
      for (const [key, label, unit] of [['f0_spread_semitones', 'Pitch spread', ' semitones'], ['voiced_energy_spread_db', 'Voiced energy spread', ' dB']]) {
        const value = evidence.metrics?.[key]; metric($('experimentalValues'), label, Number.isFinite(value) ? value.toFixed(2) + unit : 'Unavailable');
        const reference = evidence.personal_reference?.[key];
        if (reference && Number.isFinite(reference.reference_median) && Number.isFinite(reference.difference)) {
          const card = $('experimentalValues').lastElementChild;
          paragraph(card, `Your reference: ${reference.reference_median.toFixed(2)}${unit} · difference ${reference.difference >= 0 ? '+' : ''}${reference.difference.toFixed(2)}${unit}`, 'z');
        }
      }
      $('qualityFlags').textContent = evidence.quality_flags?.length ? 'Capture / tracking flags: ' + evidence.quality_flags.map(flag => flag.replaceAll('_', ' ')).join(', ') : 'No configured capture flags were raised. This does not verify every aspect of recording quality.';
      if (evidence.personal_reference?.available === false) $('qualityFlags').textContent += ' A personal experimental reference is not available for this recording.';
    }
  }
  function paragraph(parent, text, className = '') { const item = document.createElement('p'); item.textContent = text; if (className) item.className = className; parent.append(item); }
  function appendSources(parent, sources) {
    const footnote = document.createElement('div'); footnote.className = 'source';
    sources.forEach((source, index) => {
      if (index) footnote.append(document.createTextNode(' · '));
      let address = null;
      try { const parsed = new URL(source.url); if (['http:', 'https:'].includes(parsed.protocol)) address = parsed.href; } catch { /* Legacy snapshots have only source IDs. */ }
      const label = source.version || source.id || 'Source';
      if (address) { const link = document.createElement('a'); link.href = address; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = label; footnote.append(link); }
      else { const text = document.createElement('span'); text.textContent = label; footnote.append(text); }
      if (source.excerpt) { const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Source excerpt'; details.append(summary); paragraph(details, source.excerpt); footnote.append(details); }
    });
    if (sources.length) parent.append(footnote);
  }
  function noteText(note) {
    const measured = note.measured?.features ? Object.entries(featureLabels).filter(([key]) => Number.isFinite(note.measured.features[key])).map(([key, [label, format]]) => `${label}: ${format(note.measured.features[key])}`).join('. ') : typeof note.measured === 'string' ? note.measured : 'Measurement details are recorded separately.';
    return `Measured. ${measured}. You said. ${(Array.isArray(note.patient_said) ? note.patient_said : [note.patient_said]).filter(Boolean).join('. ')}. Still unclear. ${(note.unresolved || []).join('. ') || 'No additional uncertainty was recorded.'}${note.patient_correction ? '. Your correction. ' + note.patient_correction : ''}`;
  }
  function renderSession(value, { autoplay = true } = {}) {
    session = value; saveConnection(); $('conversationPanel').hidden = false;
    renderMeasured(value.measured); $('turnHistory').replaceChildren();
    for (const turn of value.turns || []) {
      if (!turn.answered_at && !turn.closed_at) continue;
      const block = document.createElement('div'); block.className = 'turn';
      paragraph(block, turn.question.text); paragraph(block, turn.skipped || !turn.answered_at ? 'You skipped or left this question unanswered.' : turn.answer || '', 'answer');
      appendSources(block, turn.question.sources || []);
      $('turnHistory').append(block);
    }
    const turn = value.turns?.find(item => !item.answered_at && !item.closed_at);
    $('questionPanel').hidden = value.state !== 'active' || !turn;
    $('questionText').textContent = turn?.question.text || '';
    $('questionSources').replaceChildren(); if (turn) appendSources($('questionSources'), turn.question.sources || []);
    clearAnswer();
    voice.announce(turn?.question.text || '', value.session_id + ':' + (turn?.turn_id || 'closed'), Boolean(turn && autoplay && $('voiceEnabled').checked), ttsRequest());
    $('conversationState').textContent = value.state === 'abstained' ? 'No further supported question was selected. Uncertainty remains in your note.' : value.state === 'complete' ? 'The question sequence has ended. Please review your note.' : value.state === 'confirmed' ? 'Your note is confirmed and saved.' : '';
    $('notePanel').hidden = !value.note;
    if (value.note) {
      const note = value.note;
      for (const id of ['noteMeasured', 'noteSaid', 'noteUnresolved']) $(id).replaceChildren();
      if (note.measured?.features) {
        for (const [key, [label, format]] of Object.entries(featureLabels)) if (Number.isFinite(note.measured.features[key])) paragraph($('noteMeasured'), label + ': ' + format(note.measured.features[key]));
      } else paragraph($('noteMeasured'), typeof note.measured === 'string' ? note.measured : 'Measurement details appear above.');
      const answers = Array.isArray(note.patient_said) ? note.patient_said : [note.patient_said];
      for (const answer of answers.filter(Boolean)) paragraph($('noteSaid'), answer);
      if (!answers.filter(Boolean).length) paragraph($('noteSaid'), 'No answer recorded.');
      for (const item of note.unresolved || []) paragraph($('noteUnresolved'), item);
      if (!note.unresolved?.length) paragraph($('noteUnresolved'), 'No additional uncertainty was recorded.');
      $('savedCorrection').hidden = !note.patient_correction;
      $('correctionContent').textContent = note.patient_correction || '';
      $('correctionPanel').hidden = !['complete', 'abstained'].includes(value.state);
      $('correctionText').value = '';
      $('noteStatus').textContent = `Revision ${value.revision} · ${value.state === 'confirmed' ? 'Confirmed' : 'Not yet confirmed'}`;

    }
    updateControls();
  }
  async function refreshHistory() {
    if (!connected || !enrolled) { $('historyList').replaceChildren(); paragraph($('historyList'), 'No saved check-ins yet. Enroll and record your first reading.', 'empty'); return; }
    const binding = connected;
    const data = await request(binding, profilePath(binding, '/history'));
    $('historyList').replaceChildren();
    for (const item of data.checkins || []) {
      const row = document.createElement('div'); row.className = 'history-row';
      const text = document.createElement('div');
      paragraph(text, new Date(item.time).toLocaleString());
      const details = document.createElement('details'), summary = document.createElement('summary');
      summary.textContent = 'View saved measurements'; details.append(summary);
      for (const [key, [label, format]] of Object.entries(featureLabels)) {
        const value = item.measured?.features?.[key], reference = item.measured?.reference_median?.[key];
        if (Number.isFinite(value)) paragraph(details, `${label}: ${format(value)}${Number.isFinite(reference) ? ' | Personal reference: ' + format(reference) : ''}`, 'small muted');
      }
      text.append(details);
      paragraph(text, item.measured?.deviation_from_baseline === 'persistent' ? 'A repeated timing change was noticed' : item.measured?.deviation_from_baseline === 'elevated' ? 'Reading differs from your reference; repetition threshold not met' : item.measured?.deviation_from_baseline === 'usual' ? 'Reading saved · within your usual range' : 'Reading saved · classification unavailable', 'muted');
      if (item.conversation) {
        paragraph(text, item.conversation.state === 'confirmed' ? 'Note confirmed' : 'Conversation: ' + item.conversation.state, 'small muted');
        const open = document.createElement('button'); open.className = 'secondary'; open.textContent = item.conversation.state === 'active' ? 'Continue conversation' : 'View note'; open.dataset.openSession = '';
        open.onclick = () => task(async () => { const restored = await request(binding, profilePath(binding, '/conversations/' + item.conversation.session_id)); renderSession(restored, { autoplay: false }); switchView('checkin'); $('conversationPanel').scrollIntoView({ block: 'start', behavior: 'smooth' }); });
        row.append(text, open);
      } else {
        const open = document.createElement('button'); open.className = 'secondary'; open.textContent = 'Open question'; open.dataset.openSession = '';
        open.onclick = () => task(async () => { renderSession(await request(binding, profilePath(binding, '/conversations'), { method: 'POST', body: { checkin_time: item.time } })); switchView('checkin'); });
        row.append(text, open);
      }
      $('historyList').append(row);
    }
    for (const report of data.reports || []) {
      const row = document.createElement('div'); row.className = 'history-row'; const text = document.createElement('div');
      paragraph(text, 'Personal note · ' + new Date(report.created_at).toLocaleString()); paragraph(text, report.report_text, 'muted'); row.append(text); $('historyList').append(row);
    }
    if (!(data.checkins?.length || data.reports?.length)) paragraph($('historyList'), 'No saved check-ins yet. Your first reading will appear here.', 'empty');
    updateControls();
  }
  function switchView(view) {
    $('checkinView').hidden = view !== 'checkin'; $('historyView').hidden = view !== 'history';
    for (const [id, active] of [['checkinBtn', view === 'checkin'], ['historyBtn', view === 'history']]) { $(id).classList.toggle('selected', active); $(id).setAttribute('aria-pressed', String(active)); }
  }
  function ttsRequest() {
    const binding = connected;
    return capabilities.tts_enabled ? (text, signal) => request(binding, '/speak', { method: 'POST', body: { text: text.slice(0, 5000) }, audio: true, signal, timeoutMs: 35000 }) : null;
  }
  async function speak(text) { return voice.speak(text, ttsRequest()); }
  $('voiceEnabled').onchange = () => { voice.stop(); try { localStorage.setItem('cadence.voice.enabled', String($('voiceEnabled').checked)); } catch { /* Preference only. */ } };
  $('pauseSpeechBtn').onclick = () => voice.pause();
  $('stopSpeechBtn').onclick = () => voice.stop();
  $('typeAnswerBtn').onclick = () => { voice.stop(); $('answerText').focus(); };
  $('answerText').oninput = updateControls;
  $('answerPreview').onplay = () => voice.stop();
  $('cancelAnswerBtn').onclick = () => {
    const capture = recording?.kind === 'answer' ? recording : pendingAnswer;
    if (!capture) return;
    capture.cancelled = true; capture.controller?.abort();
    if (capture.recorder.state !== 'inactive') stopRecording();
    capture.stream.getTracks().forEach(track => track.stop());
    clearAnswer(false); $('answerStatus').textContent = 'Recording canceled. Your typed answer is unchanged.';
    message('Recording canceled. No transcript was submitted.'); updateControls();
  };
  $('connectBtn').onclick = () => task(connect);
  $('freshProfileBtn').onclick = () => task(async () => {
    $('profileId').value = 'judge-' + crypto.randomUUID();
    await connect(); switchView('checkin'); $('captureHeading').scrollIntoView({ block: 'center', behavior: 'smooth' });
  });
  $('newProfileBtn').onclick = () => { if (busy || recording || pending()) return; $('profileId').value = 'demo-' + crypto.randomUUID().slice(0, 8); $('connectionSettings').open = true; $('profileId').focus(); updateControls(); message('New ID prepared. Choose Connect to start a new reference; existing history is preserved.'); };
  $('captureKind').onchange = updateControls;
  $('apiBase').oninput = updateControls; $('profileId').oninput = updateControls;
  $('recordBtn').onclick = () => task(() => startRecording($('captureKind').value));
  $('recordAnswerBtn').onclick = () => task(() => startRecording('answer'));
  $('stopBtn').onclick = stopRecording; $('stopAnswerBtn').onclick = stopRecording;
  $('enrollBtn').onclick = () => task(async () => {
    const binding = connected, form = new FormData();
    references.forEach((take, i) => form.append('files', take.blob, `reference-${i + 1}.wav`)); form.append('condition', 'parkinsons');
    message('Saving your personal reference…');
    const params = new URLSearchParams();
    if ($('experimentalToggle').checked) params.set('experimental', 'true');
    if (capabilities.asr_enabled && $('verifyPassageToggle').checked) params.set('verify_passage', 'true');
    await request(binding, profilePath(binding, '/enroll' + (params.size ? '?' + params : '')), { method: 'POST', body: form });
    baselineMedian = {}; // The scored check-in supplies the actual fitted reference values.
    enrolled = true; compatible = true; clearTakes(); $('captureKind').value = 'checkin';
    $('captureHeading').textContent = 'Your daily reading'; $('captureHelp').textContent = 'Read at your comfortable pace. We compare with your own reference.';
    $('profileStatus').textContent = 'Reference ready'; $('routineNotePanel').hidden = false;
    $('connectionSettings').open = false;
    message('Your reference is saved. Record your first check-in when ready.'); await refreshHistory();
  });
  async function submitCheckin() {
    const binding = connected, form = new FormData(); form.append('file', checkinTake.blob, 'checkin.wav');
    message('Comparing this reading with your reference…');
    const params = new URLSearchParams();
    if ($('experimentalToggle').checked) params.set('experimental', 'true');
    if (capabilities.asr_enabled && $('verifyPassageToggle').checked) params.set('verify_passage', 'true');
    const suffix = '/checkin' + (params.size ? '?' + params : '');
    const result = await request(binding, profilePath(binding, suffix), { method: 'POST', body: form });
    latestCheckin = result; renderMeasured(result.measured);
    URL.revokeObjectURL(checkinTake.url); checkinTake = null; renderTakes();
    session = null; saveConnection(); voice.stop();
    $('conversationPanel').hidden = true; $('notePanel').hidden = true;
    message('Reading saved. Review your measurements, then choose Continue to AI Conversation.');
    $('measurementPanel').scrollIntoView({ block: 'start', behavior: 'smooth' });
    await refreshHistory();
  }
  // Manual fallback/retry -- e.g. a check-in whose auto-submit failed, or a
  // take recorded with an older build. Normal use submits automatically the
  // moment a check-in recording finishes (see recorder.onstop above).
  $('uploadBtn').onclick = () => task(submitCheckin);
  $('continueConversationBtn').onclick = () => task(async () => {
    renderSession(await request(connected, profilePath(connected, '/conversations'), { method: 'POST', body: { checkin_time: latestCheckin.checkin_time } }));
    message(session.state === 'active' ? 'A question is ready. Listen, then tap to answer.' : 'No supported question was selected. Review the saved note and its uncertainties.');
    $('conversationPanel').scrollIntoView({ block: 'start', behavior: 'smooth' });
  });
  async function submitAnswer(text) {
    const binding = connected, active = session, turn = active.turns.find(item => !item.answered_at && !item.closed_at);
    if (!text) throw new Error('Type an answer, or record one and review its transcript first.');
    const key = turn.turn_id + '\n' + text;
    const submission = retryAnswers.get(key) || crypto.randomUUID(); retryAnswers.set(key, submission);
    message('Saving your answer and selecting the next supported question…');
    const result = await request(binding, sessionPath(binding, active) + '/turns/' + turn.turn_id + '/answer', { method: 'POST', body: { submission_id: submission, answer_text: text } });
    renderSession(result); message(result.state === 'active' ? 'Answer saved. A follow-up question is ready.' : 'Answers saved. Review the note below.'); await refreshHistory();
  }
  // Every answer, including an ASR transcript, needs explicit patient confirmation.
  $('answerBtn').onclick = () => task(() => submitAnswer($('answerText').value.trim()));
  $('skipQuestionBtn').onclick = () => task(async () => {
    voice.stop(); const turn = session.turns.find(item => !item.answered_at && !item.closed_at);
    const key = turn.turn_id + ':skip'; const submission = retryAnswers.get(key) || crypto.randomUUID(); retryAnswers.set(key, submission);
    renderSession(await request(connected, sessionPath() + '/turns/' + turn.turn_id + '/answer', { method: 'POST', body: { submission_id: submission, skipped: true } }));
    message('Question skipped. It will remain unanswered in your note.'); await refreshHistory();
  });
  $('confirmBtn').onclick = () => task(async () => {
    const result = await request(connected, sessionPath() + '/confirm', { method: 'POST', body: { revision: session.revision } });
    renderSession(result); message('Your reviewed note is confirmed and saved.'); await refreshHistory();
  });
  $('finishConversationBtn').onclick = () => task(async () => {
    voice.stop(); const result = await request(connected, sessionPath() + '/finish', { method: 'POST', body: { revision: session.revision } });
    renderSession(result); message('Conversation saved for now. Review the note; unanswered details remain unclear.'); await refreshHistory();
  });
  $('resetCheckinBtn').onclick = () => task(async () => {
    // Preserve the previous conversation as a draft. Starting another check-in
    // is not approval of an unreviewed note; only Confirm can grant that state.
    if (session.state === 'active') session = await request(connected, sessionPath() + '/finish', { method: 'POST', body: { revision: session.revision } });
    session = null; saveConnection();
    $('conversationPanel').hidden = true; $('notePanel').hidden = true;
    message('Your previous check-in was saved as an unconfirmed draft. Ready to record a new one.'); await refreshHistory();
  });
  $('correctionBtn').onclick = () => task(async () => {
    const text = $('correctionText').value.trim(); if (!text) throw new Error('Enter the correction you want to add.');
    const result = await request(connected, sessionPath() + '/correction', { method: 'POST', body: { revision: session.revision, correction_text: text } });
    renderSession(result); message('Correction saved. Review the updated note before confirming.');
  });
  $('saveRoutineNoteBtn').onclick = () => task(async () => {
    const text = $('routineNoteText').value.trim(); if (!text) throw new Error('Write the note you want to save.');
    await request(connected, profilePath(connected, '/reports'), { method: 'POST', body: { report_text: text } });
    $('routineNoteText').value = ''; $('routineNoteStatus').textContent = 'Your words are saved as a personal note.'; message('Personal note saved.'); await refreshHistory();
  });
  $('speakQuestionBtn').onclick = () => task(() => speak($('questionText').textContent));
  $('speakNoteBtn').onclick = () => task(() => speak(noteText(session.note)));
  $('checkinBtn').onclick = () => switchView('checkin');
  $('historyBtn').onclick = () => { switchView('history'); if (!busy && !recording) task(refreshHistory); };
  $('refreshHistoryBtn').onclick = () => task(refreshHistory);
  window.addEventListener('pagehide', () => {
    voice.clear();
    if (pendingAnswer) { pendingAnswer.cancelled = true; pendingAnswer.controller?.abort(); }
    if (recording) { recording.cancelled = true; recording.stream.getTracks().forEach(track => track.stop()); }
    clearAnswer(); clearTakes();
  });
  $('connectionSettings').open = true; updateControls(); task(connect);
})();
