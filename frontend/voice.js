'use strict';
// Playback only. Patient audio never enters this controller or its short-lived cache.
window.CadenceVoice = class CadenceVoice {
  constructor(player, onState) {
    this.player = player; this.onState = onState; this.state = 'idle';
    this.generation = 0; this.cache = new Map(); this.settle = null;
    this.voice = null; this.provider = ''; this.controller = null;
    try { this.seen = new Set(JSON.parse(sessionStorage.getItem('cadence.voice.seen') || '[]')); }
    catch { this.seen = new Set(); }
  }
  get active() { return ['loading', 'speaking', 'paused'].includes(this.state); }
  setState(state, label) { this.state = state; this.onState(state, label); }
  remember(key) {
    this.seen.add(key);
    this.seen = new Set([...this.seen].slice(-100));
    try { sessionStorage.setItem('cadence.voice.seen', JSON.stringify([...this.seen])); } catch { /* Private browsing. */ }
  }
  announce(text, key, automatic, request) {
    if (this.currentKey !== key) this.stop();
    this.currentKey = key;
    const alreadySeen = this.seen.has(key); this.remember(key);
    if (automatic && !alreadySeen) void this.speak(text, request);
  }
  stop() {
    this.generation++; this.controller?.abort(); this.controller = null;
    clearTimeout(this.timer);
    this.player.onended = this.player.onerror = null;
    this.player.pause(); this.player.removeAttribute('src'); this.player.load();
    if (this.usingBrowser) window.speechSynthesis?.cancel();
    this.usingBrowser = false;
    const settle = this.settle; this.settle = null; settle?.(false);
    this.setState('idle', 'Cadence is quiet. Tap to answer when you are ready.');
  }
  clear() {
    this.stop(); this.currentKey = null;
    for (const url of this.cache.values()) URL.revokeObjectURL(url);
    this.cache.clear();
  }
  pause() {
    if (this.state === 'speaking') {
      if (this.usingBrowser) window.speechSynthesis.pause(); else this.player.pause();
      this.setState('paused', 'Cadence is paused. Resume or stop before recording.');
    } else if (this.state === 'paused') {
      if (this.usingBrowser) window.speechSynthesis.resume();
      else this.player.play().catch(() => this.stop());
      this.setState('speaking', 'Cadence is speaking. ' + this.provider);
    }
  }
  chooseBrowserVoice() {
    const all = window.speechSynthesis.getVoices();
    if (this.voice && all.some(v => v.voiceURI === this.voice.voiceURI)) return this.voice;
    const english = all.filter(v => /^en[-_]US$/i.test(v.lang));
    const preferred = v => /zira|jenny|aria|samantha|ava|joanna|susan|female/i.test(v.name);
    this.voice = english.find(v => v.localService && preferred(v)) || english.find(preferred)
      || english.find(v => v.localService) || english[0] || all.find(v => /^en/i.test(v.lang));
    return this.voice;
  }
  async speak(text, request) {
    this.stop(); text = text.trim(); if (!text) return false;
    const generation = this.generation;
    this.controller = new AbortController();
    this.setState('loading', 'Preparing Cadence\u2019s voice\u2026');
    let url = this.cache.get(text);
    try {
      if (!url && request) {
        const blob = await request(text, this.controller.signal);
        if (generation !== this.generation) return false;
        url = URL.createObjectURL(blob); this.cache.set(text, url);
        if (this.cache.size > 8) {
          const oldest = this.cache.keys().next().value;
          URL.revokeObjectURL(this.cache.get(oldest)); this.cache.delete(oldest);
        }
      }
    } catch (error) {
      if (generation !== this.generation || error.name === 'AbortError') return false;
      // Provider errors never hide the question or block the typed-answer path.
    }
    if (generation !== this.generation) return false;
    if (url) {
      this.provider = 'ElevenLabs voice'; this.usingBrowser = false;
      this.player.src = url;
      return new Promise(resolve => {
        this.settle = resolve;
        const finish = () => {
          if (generation !== this.generation) return;
          clearTimeout(this.timer); this.settle = null;
          this.setState('idle', 'Cadence has finished. Tap to answer.'); resolve(true);
        };
        this.player.onended = finish;
        this.player.onerror = () => { this.stop(); this.setState('unavailable', 'Audio could not play. Read the question or try Replay.'); };
        this.player.play().then(() => {
          if (generation !== this.generation) return;
          this.setState('speaking', 'Cadence is speaking. ' + this.provider);
          this.timer = setTimeout(() => this.stop(), Math.min(180000, text.length * 120 + 15000));
        }).catch(() => {
          if (generation !== this.generation) return;
          this.stop(); this.setState('blocked', 'Playback needs your permission. Choose Replay question, or read it below.');
        });
      });
    }
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      this.setState('unavailable', 'Spoken playback is unavailable. The question is shown below; you can type your answer.');
      return false;
    }
    // Some browsers populate voices after page load. Never claim a specific voice if unavailable.
    if (!window.speechSynthesis.getVoices().length) await new Promise(resolve => setTimeout(resolve, 300));
    if (generation !== this.generation) return false;
    const chosen = this.chooseBrowserVoice();
    const utterance = new SpeechSynthesisUtterance(text);
    if (chosen) utterance.voice = chosen;
    utterance.lang = 'en-US'; utterance.rate = 0.92; utterance.pitch = 1;
    this.usingBrowser = true;
    this.provider = 'Browser voice fallback' + (chosen ? ': ' + chosen.name : ' (system default)');
    return new Promise(resolve => {
      this.settle = resolve;
      utterance.onstart = () => {
        if (generation === this.generation) this.setState('speaking', 'Cadence is speaking. ' + this.provider);
      };
      utterance.onend = () => {
        if (generation !== this.generation) return;
        clearTimeout(this.timer); this.settle = null; this.usingBrowser = false;
        this.setState('idle', 'Cadence has finished. ' + this.provider + '. Tap to answer.'); resolve(true);
      };
      utterance.onerror = () => {
        if (generation !== this.generation) return;
        this.stop(); this.setState('blocked', 'Browser voice could not play. Choose Replay question, or continue by typing.');
      };
      this.timer = setTimeout(() => {
        if (generation === this.generation) { this.stop(); this.setState('unavailable', 'Spoken playback timed out. You can read the question and continue.'); }
      }, Math.min(180000, text.length * 120 + 15000));
      window.speechSynthesis.speak(utterance);
    });
  }
};
