'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let busy = false, connected = null, enrolled = false, compatible = true, capabilities = {};
  let session = null, latestMeasured = null, latestCheckin = null;
  let recording = null, checkinTake = null, speechUrl = null;
  // Which turn/note has already been spoken aloud this page session -- so a
  // re-render (reload recovery, confirm(), unrelated updates) doesn't replay
  // audio for a question the patient already heard.
  let spokenTurnId = null, spokenNoteSessionId = null;
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
    for (const id of ['apiBase', 'profileId', 'connectBtn', 'newProfileBtn']) $(id).disabled = locked || hasPending;
    $('captureKind').disabled = locked || hasPending;
    $('recordBtn').disabled = locked || !configured || !compatible || hasPending || ($('captureKind').value === 'reference' && references.length >= 5);
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
    $('answerBtn').disabled = locked || session?.state !== 'active' || !turn;
    $('finishConversationBtn').disabled = locked || session?.state !== 'active';
    $('answerText').disabled = locked || session?.state !== 'active';
    $('recordAnswerBtn').disabled = locked || session?.state !== 'active' || !turn;
    $('recordAnswerBtn').hidden = !capabilities.asr_enabled;
    $('asrHelp').hidden = false;
    $('asrHelp').textContent = capabilities.asr_enabled ? 'A recorded answer is transcribed for you to review. It is sent only when you choose Send answer.' : 'Optional answer transcription is unavailable on this service. You can type your answer above.';
    $('stopAnswerBtn').hidden = !recording || recording.kind !== 'answer';
    $('confirmBtn').disabled = locked || !session || !['complete', 'abstained'].includes(session.state);
    $('confirmBtn').hidden = session?.state === 'confirmed';
    $('correctionBtn').disabled = locked || !session || !['complete', 'abstained'].includes(session.state);
    $('correctionText').disabled = locked;
    $('saveRoutineNoteBtn').disabled = locked || !configured || !enrolled;
    $('routineNoteText').disabled = locked;
    $('refreshHistoryBtn').disabled = locked || !connected;
    $('speakQuestionBtn').disabled = locked;
    $('speakNoteBtn').disabled = locked;
    $('speakQuestionBtn').hidden = !capabilities.tts_enabled;
    $('speakNoteBtn').hidden = !capabilities.tts_enabled;
    document.querySelectorAll('[data-remove], [data-open-session]').forEach(button => { button.disabled = locked; });
  }
  async function task(operation) {
    if (busy || recording) return;
    busy = true; error(''); updateControls();
    try { await operation(); } catch (problem) { error(problem.message || 'The request could not be completed.'); }
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
  async function request(binding, path, { method = 'GET', body, audio = false, allow404 = false } = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000);
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
      if (problem.name === 'AbortError') throw new Error('The service took too long to respond. Your typed answer is still here; retry when ready.');
      if (problem instanceof TypeError) throw new Error('Cannot reach the API. Check the address and that the backend is running.');
      throw problem;
    } finally { clearTimeout(timeout); }
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
    const profile = await request(binding, profilePath(binding), { allow404: true });
    clearTakes();
    connected = Object.freeze(binding); capabilities = caps;
    $('verifyPassageLabel').hidden = !caps.asr_enabled; enrolled = Boolean(profile); compatible = profile?.baseline_compatible !== false && (!profile || profile.condition === 'parkinsons');
    session = null; latestMeasured = null; latestCheckin = null;
    $('measurementPanel').hidden = true; $('conversationPanel').hidden = true; $('notePanel').hidden = true;
    $('routineNotePanel').hidden = !enrolled;
    $('passageText').textContent = caps.passage?.text || 'Passage unavailable; reconnect before recording.';
    $('passageMeta').textContent = caps.passage ? `${caps.passage.syllable_count} fixed syllables · use this exact passage for reference and check-in` : '';
    $('profileStatus').textContent = enrolled ? (compatible ? 'Reference ready · ' + binding.profile : 'Older reference · new profile needed') : 'New profile · ' + binding.profile;
    $('captureHeading').textContent = enrolled ? 'Your daily reading' : 'Get to know your usual';
    $('captureHelp').textContent = enrolled ? 'Read at your comfortable pace. We compare with your own reference.' : 'Record 3–5 comfortable readings to make your personal reference.';
    $('captureKind').value = enrolled ? 'checkin' : 'reference';
    if (profile && !compatible) error('This profile uses a legacy condition or reference protocol. Choose a new profile ID for the Parkinson’s self-check. Existing history is preserved.');
    if (stored.base === binding.base && stored.profile === binding.profile && stored.session) {
      const restored = await request(binding, profilePath(binding, '/conversations/' + encodeURIComponent(stored.session)), { allow404: true });
      if (restored) renderSession(restored);
    }
    saveConnection();
    $('connectionSettings').open = !enrolled || !compatible;
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
    if (kind === 'checkin' && capabilities.tts_enabled) {
      // The AI should ask you to read, out loud, before the mic opens --
      // not just show text with a Record button. Speaking and recording
      // can't happen at once here: the prompt would bleed into the very
      // passage recording the trigger math depends on, so this fully
      // finishes (including playback) before the microphone is requested.
      message('Listen for the prompt…');
      try { await speak('Please read today’s passage at your comfortable pace.'); } catch { /* speak() already reported a fallback */ }
    }
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
        if (capture.kind === 'checkin' && !capture.failed && checkinTake) task(submitCheckin);
      });
      recording = capture; recorder.start(500);
      capture.limit = setTimeout(() => stopRecording(), 60000);
      capture.timer = setInterval(() => { $('recordingTimer').textContent = `${Math.floor((Date.now() - capture.started) / 1000)}s · recording`; }, 1000);
      message(kind === 'answer' ? 'Recording your answer. Choose Finish answer recording when ready.' : 'Recording. Read the passage, then choose Finish recording.');
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
  async function finishRecording(capture) {
    clearTimeout(capture.limit); clearInterval(capture.timer);
    capture.stream.getTracks().forEach(track => track.stop());
    recording = null; busy = true; updateControls(); $('recordingTimer').textContent = '';
    try {
      if (capture.failed) return;
      message('Preparing your WAV recording…');
      const buffer = await capture.context.decodeAudioData(await new Blob(capture.chunks, { type: capture.recorder.mimeType }).arrayBuffer());
      const blob = encodeWav(buffer);
      if (capture.kind === 'answer') {
        if (session?.session_id !== capture.activeSession?.session_id) throw new Error('The conversation changed; record the answer again.');
        message('Transcribing your answer for review…');
        const form = new FormData(); form.append('file', blob, 'answer.wav');
        const result = await request(capture.binding, '/transcribe', { method: 'POST', body: form });
        if (!result.text?.trim()) throw new Error('No words were transcribed. You can type your answer or record again.');
        $('answerText').value = result.text.trim();
        message('Transcript ready. Review or edit it, then choose Send answer.'); $('answerText').focus();
      } else {
        const take = { blob, seconds: buffer.duration, url: URL.createObjectURL(blob) };
        if (capture.kind === 'reference') references.push(take);
        else { if (checkinTake) URL.revokeObjectURL(checkinTake.url); checkinTake = take; }
        renderTakes(); message(capture.kind === 'reference' ? `${references.length} reference reading${references.length === 1 ? '' : 's'} ready. Save after 3–5 takes.` : 'Your check-in recording is ready to compare.');
      }
    } catch (problem) { error(problem.message || 'Could not decode this recording. Try another supported browser.'); }
    finally { await capture.context.close(); busy = false; updateControls(); }
  }
  function renderTakes() {
    $('takeList').replaceChildren();
    [...references.map((take, i) => [take, `Reference ${i + 1}`]), ...(checkinTake ? [[checkinTake, 'Today’s reading']] : [])].forEach(([take, title]) => {
      const row = document.createElement('div'); row.className = 'take-row';
      const label = document.createElement('p'); label.textContent = `${title} · ${take.seconds.toFixed(1)} seconds`;
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
    }
    const status = measured.deviation_from_baseline;
    $('outcomeText').textContent = status === 'persistent' ? 'The timing persistence threshold was met. A question can help put this reading in context.' : status === 'elevated' ? 'This reading differs from your reference; the repeated-change threshold was not met.' : 'The repeated-change threshold was not met. This describes the recording, not your health.';
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
  function renderSession(value) {
    session = value; saveConnection(); $('conversationPanel').hidden = false;
    renderMeasured({ ...value.measured, deviation_from_baseline: 'persistent' }); $('turnHistory').replaceChildren();
    for (const turn of value.turns || []) {
      if (!turn.answered_at) continue;
      const block = document.createElement('div'); block.className = 'turn';
      paragraph(block, turn.question.text); paragraph(block, turn.answer || '', 'answer');
      appendSources(block, turn.question.sources || []);
      $('turnHistory').append(block);
    }
    const turn = value.turns?.find(item => !item.answered_at && !item.closed_at);
    $('questionPanel').hidden = value.state !== 'active' || !turn;
    $('questionText').textContent = turn?.question.text || '';
    $('questionSources').replaceChildren(); if (turn) appendSources($('questionSources'), turn.question.sources || []);
    $('answerText').value = '';
    // Speak the question the moment it's new, instead of making the patient
    // press a separate button to hear it -- this is what actually makes the
    // check-in feel like a conversation rather than a form to fill out.
    if (turn && turn.turn_id !== spokenTurnId) {
      spokenTurnId = turn.turn_id;
      speak(turn.question.text)
        .catch(() => message('Could not play the question aloud automatically. It is shown above; use the speaker button to try again.'))
        .then(() => {
          // Once the AI finishes asking, start listening for the answer
          // automatically instead of waiting for a separate "Record an
          // answer" press -- same reasoning as the question itself: this is
          // what makes it feel like a conversation. Falls back to the
          // existing manual button (still visible) if a mic can't be
          // opened right now, or if local transcription isn't available at
          // all, in which case typing remains the only path either way.
          if (capabilities.asr_enabled && !recording && !busy) task(() => startRecording('answer'));
        });
    }
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
      // Read the wrap-up note aloud too, once, when the sequence has ended --
      // but never while a question is still active, so the two don't talk
      // over each other.
      if (!turn && value.session_id !== spokenNoteSessionId) {
        spokenNoteSessionId = value.session_id;
        speak(noteText(note)).catch(() => message('Could not read the note aloud automatically. It is shown above; use the speaker button to try again.'));
      }
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
      paragraph(text, item.triggered ? 'Timing question opened' : 'Reading saved · repeated-change threshold not met', 'muted');
      if (item.conversation) {
        paragraph(text, item.conversation.state === 'confirmed' ? 'Note confirmed' : 'Conversation: ' + item.conversation.state, 'small muted');
        const open = document.createElement('button'); open.className = 'secondary'; open.textContent = item.conversation.state === 'active' ? 'Continue conversation' : 'View note'; open.dataset.openSession = '';
        open.onclick = () => task(async () => { const restored = await request(binding, profilePath(binding, '/conversations/' + item.conversation.session_id)); renderSession(restored); switchView('checkin'); $('conversationPanel').scrollIntoView({ block: 'start', behavior: 'smooth' }); });
        row.append(text, open);
      } else if (item.triggered) {
        const open = document.createElement('button'); open.className = 'secondary'; open.textContent = 'Open question'; open.dataset.openSession = '';
        open.onclick = () => task(async () => { renderSession(await request(binding, profilePath(binding, '/conversations'), { method: 'POST', body: { checkin_time: item.time } })); switchView('checkin'); });
        row.append(text, open);
      } else row.append(text);
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
  async function speak(text) {
    const blob = await request(connected, '/speak', { method: 'POST', body: { text: text.slice(0, 5000) }, audio: true });
    if (speechUrl) URL.revokeObjectURL(speechUrl); speechUrl = URL.createObjectURL(blob);
    const player = $('speechPlayer'); player.src = speechUrl; player.hidden = false;
    try {
      await player.play();
      // Resolve once playback actually finishes, not once it merely starts
      // (that's all Audio.play()'s own promise means) -- callers that want
      // to do something right after the AI stops talking (e.g. start
      // listening for the answer) need the real end, not the start.
      await new Promise(resolve => { player.onended = resolve; });
    } catch { message('Spoken audio is ready. Press Play below to listen.'); }
  }
  $('connectBtn').onclick = () => task(connect);
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
    enrolled = true; compatible = true; clearTakes(); $('captureKind').value = 'checkin';
    $('captureHeading').textContent = 'Your daily reading'; $('captureHelp').textContent = 'Read at your comfortable pace. We compare with your own reference.';
    $('profileStatus').textContent = 'Reference ready · ' + binding.profile; $('routineNotePanel').hidden = false;
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
    if (result.status === 'awaiting_answer') {
      renderSession(await request(binding, profilePath(binding, '/conversations'), { method: 'POST', body: { checkin_time: result.checkin_time } }));
      message('A question is ready.'); $('questionText').scrollIntoView({ block: 'center', behavior: 'smooth' });
    } else {
      session = null; saveConnection(); $('conversationPanel').hidden = true; $('notePanel').hidden = true;
      message('Reading saved. The repeated-change threshold was not met. You can still add a personal note.');
    }
    await refreshHistory();
  }
  // Manual fallback/retry -- e.g. a check-in whose auto-submit failed, or a
  // take recorded with an older build. Normal use submits automatically the
  // moment a check-in recording finishes (see recorder.onstop above).
  $('uploadBtn').onclick = () => task(submitCheckin);
  $('answerBtn').onclick = () => task(async () => {
    const binding = connected, active = session, turn = active.turns.find(item => !item.answered_at && !item.closed_at);
    const text = $('answerText').value.trim(); if (!text) throw new Error('Type an answer, or record one and review its transcript first.');
    const key = turn.turn_id + '\n' + text;
    const submission = retryAnswers.get(key) || crypto.randomUUID(); retryAnswers.set(key, submission);
    message('Saving your answer and selecting the next supported question…');
    const result = await request(binding, sessionPath(binding, active) + '/turns/' + turn.turn_id + '/answer', { method: 'POST', body: { submission_id: submission, answer_text: text } });
    renderSession(result); message(result.state === 'active' ? 'Answer saved. A follow-up question is ready.' : 'Answers saved. Review the note below.'); await refreshHistory();
  });
  $('confirmBtn').onclick = () => task(async () => {
    const result = await request(connected, sessionPath() + '/confirm', { method: 'POST', body: { revision: session.revision } });
    renderSession(result); message('Your reviewed note is confirmed and saved.'); await refreshHistory();
  });
  $('finishConversationBtn').onclick = () => task(async () => {
    const result = await request(connected, sessionPath() + '/finish', { method: 'POST', body: { revision: session.revision } });
    renderSession(result); message('Conversation saved for now. Review the note; unanswered details remain unclear.'); await refreshHistory();
  });
  $('resetCheckinBtn').onclick = () => task(async () => {
    // Save the open conversation through the same finish/confirm steps a
    // patient could do by hand (nothing is discarded), then clear it from
    // the screen so a new check-in can start. Not a delete -- a shortcut.
    if (session.state === 'active') session = await request(connected, sessionPath() + '/finish', { method: 'POST', body: { revision: session.revision } });
    if (['complete', 'abstained'].includes(session.state)) session = await request(connected, sessionPath() + '/confirm', { method: 'POST', body: { revision: session.revision } });
    session = null; saveConnection();
    $('conversationPanel').hidden = true; $('notePanel').hidden = true;
    message('Your previous check-in was saved. Ready to record a new one.'); await refreshHistory();
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
  window.addEventListener('pagehide', () => { if (recording) recording.stream.getTracks().forEach(track => track.stop()); });
  $('connectionSettings').open = true; updateControls(); task(connect);
})();
