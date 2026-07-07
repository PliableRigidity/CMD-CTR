/**
 * SentenceStreamTTS — sentence-level streaming TTS engine.
 *
 * Architecture inspired by llm-voice-assistant (AGPL-3.0) latency strategy:
 *   stream tokens → detect sentences → TTS each sentence immediately
 *   play first sentence while LLM is still generating the rest
 *
 * No AGPL code copied. This is an independent implementation.
 *
 * Usage:
 *   const tts = new SentenceStreamTTS({ turnId, synthesize, onSpeakingChange });
 *   tts.feed(token);    // from SSE token handler
 *   tts.flush();        // from SSE done handler
 *   tts.feedFull(text); // for instant tool responses
 *   tts.cancel();       // for barge-in / stop / new query
 */

const SENTENCE_END_RE = /([^.!?]*[.!?]+["']?)\s+/g;
const MARKDOWN_RE = /\*\*|__|\*|#+|`{1,3}|\[([^\]]+)\]\([^)]+\)/g;

const MAX_SENTENCES = 3;
const TTS_TIMEOUT_MS = 8000;
const BACKEND = `http://${window.location.hostname}:8001`;

// Role label guard — rejects text that looks like chat history
const HISTORY_ROLE_RE = /\b(user|assistant|system)\s*:/i;

// ── Module-level diagnostics (survives instance lifecycle) ─────────────────
const _diag = {
  activeTurnId: null,
  queueSize: 0,
  currentlyPlaying: false,
  pendingChunks: 0,
  cancelledTurns: [],
  lastTextSentToTts: null,
  lastTtsError: null,
  totalTurns: 0,
  totalChunksSent: 0,
  historyRejections: 0,
  provider: "speaches",
};

export function getTTSDiagnostics() {
  return { ..._diag };
}

function _pushDiag() {
  fetch(`${BACKEND}/api/voice/tts-diagnostics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(_diag),
  }).catch(() => {});
}

// ── Helpers ────────────────────────────────────────────────────────────────

function cleanForSpeech(text) {
  return text
    .replace(MARKDOWN_RE, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function splitSentences(text) {
  const parts = text.match(/[^.!?]+[.!?]+/g);
  if (!parts || parts.length === 0) return [text.trim()].filter(Boolean);
  return parts.map((p) => p.trim()).filter(Boolean);
}

// ── Main class ─────────────────────────────────────────────────────────────

export class SentenceStreamTTS {
  constructor({ turnId, synthesize, onSpeakingChange, onLatency }) {
    this._turnId = turnId || `vt_${Date.now()}`;
    this._synthesize = synthesize;
    this._onSpeakingChange = onSpeakingChange;
    this._onLatency = onLatency || (() => {});

    this._buf = "";
    this._sentenceCount = 0;
    this._audioQueue = [];
    this._ctx = null;
    this._currentSrc = null;
    this._playing = false;
    this._cancelled = false;
    this._bargeCleanup = null;

    this._t0 = Date.now();
    this._latency = { firstSentenceMs: null, firstAudioMs: null, totalSentences: 0 };

    // Update module diagnostics
    _diag.activeTurnId = this._turnId;
    _diag.queueSize = 0;
    _diag.currentlyPlaying = false;
    _diag.totalTurns++;

    console.info(`[TTS_TURN_START] turn_id=${this._turnId}`);
    _pushDiag();
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  feed(token) {
    if (this._cancelled || this._sentenceCount >= MAX_SENTENCES) return;
    this._buf += token;
    this._extractSentences();
  }

  flush() {
    if (this._cancelled) return;
    const remaining = cleanForSpeech(this._buf);
    this._buf = "";
    if (remaining && this._sentenceCount < MAX_SENTENCES) {
      this._queueTTS(remaining);
    }
    this._ensurePlaying();
  }

  feedFull(text) {
    if (this._cancelled) return;
    const sentences = splitSentences(cleanForSpeech(text));
    for (const s of sentences) {
      if (this._sentenceCount >= MAX_SENTENCES) break;
      this._queueTTS(s);
    }
    this._buf = "";
    this._ensurePlaying();
  }

  cancel() {
    if (this._cancelled) return;
    this._cancelled = true;
    this._stopBargeIn();

    if (this._currentSrc) {
      try { this._currentSrc.stop(); } catch {}
      this._currentSrc = null;
    }
    if (this._ctx) {
      this._ctx.close().catch(() => {});
      this._ctx = null;
    }

    _diag.activeTurnId = null;
    _diag.currentlyPlaying = false;
    _diag.queueSize = 0;
    if (!_diag.cancelledTurns.includes(this._turnId)) {
      _diag.cancelledTurns = [this._turnId, ..._diag.cancelledTurns].slice(0, 5);
    }

    console.info(`[TTS_CANCEL] turn_id=${this._turnId}`);
    _pushDiag();
    this._onSpeakingChange(false);
  }

  attachBargeIn(micStream) {
    if (this._cancelled || !this._ctx) return;
    const analyser = this._ctx.createAnalyser();
    analyser.fftSize = 512;
    try {
      this._ctx.createMediaStreamSource(micStream).connect(analyser);
    } catch { return; }
    const data = new Float32Array(analyser.fftSize);
    let count = 0;

    const timer = setInterval(() => {
      if (!this._currentSrc || this._cancelled) { clearInterval(timer); return; }
      analyser.getFloatTimeDomainData(data);
      const rms = Math.sqrt(data.reduce((s, v) => s + v * v, 0) / data.length);
      if (rms > 0.018) {
        count++;
        if (count >= 4) { clearInterval(timer); this.cancel(); }
      } else {
        count = Math.max(0, count - 1);
      }
    }, 50);

    this._bargeCleanup = () => clearInterval(timer);
  }

  get isActive() {
    return !this._cancelled && (this._playing || this._audioQueue.length > 0);
  }

  // ── Internal ───────────────────────────────────────────────────────────────

  _extractSentences() {
    SENTENCE_END_RE.lastIndex = 0;
    let match;
    let consumed = 0;

    while ((match = SENTENCE_END_RE.exec(this._buf)) !== null) {
      if (this._sentenceCount >= MAX_SENTENCES) break;
      const sentence = cleanForSpeech(match[1]);
      if (sentence) {
        this._queueTTS(sentence);
        consumed = match.index + match[0].length;
      }
    }

    if (consumed > 0) {
      this._buf = this._buf.slice(consumed);
      this._ensurePlaying();
    }
  }

  _queueTTS(text) {
    if (!text) return;

    // Guard: reject text that looks like chat history
    if (HISTORY_ROLE_RE.test(text)) {
      _diag.historyRejections++;
      _diag.lastTtsError = `rejected_history_text: "${text.slice(0, 60)}"`;
      console.error(`[TTS_REJECTED_HISTORY_TEXT] turn_id=${this._turnId} text="${text.slice(0, 100)}"`);
      _pushDiag();
      return;
    }

    if (this._sentenceCount === 0) {
      this._latency.firstSentenceMs = Date.now() - this._t0;
    }
    this._sentenceCount++;
    this._latency.totalSentences++;

    _diag.lastTextSentToTts = text.slice(0, 120);
    _diag.queueSize++;
    _diag.totalChunksSent++;
    console.info(`[TTS_ENQUEUE] turn_id=${this._turnId} chars=${text.length} q=${_diag.queueSize} text="${text.slice(0, 60)}"`);

    const promise = Promise.race([
      this._synthesize(text),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`TTS timeout: "${text.slice(0, 30)}"`)), TTS_TIMEOUT_MS)
      ),
    ]).catch((err) => {
      _diag.lastTtsError = err.message;
      console.warn(`[TTS_CANCEL] turn_id=${this._turnId} synthesis_failed: ${err.message}`);
      return null;
    });

    this._audioQueue.push(promise);
    _pushDiag();
  }

  _ensurePlaying() {
    if (!this._playing && this._audioQueue.length > 0 && !this._cancelled) {
      this._playLoop();
    }
  }

  async _playLoop() {
    if (this._playing) return;
    this._playing = true;
    _diag.currentlyPlaying = true;

    if (!this._ctx || this._ctx.state === "closed") {
      try {
        this._ctx = new AudioContext();
      } catch (e) {
        console.error(`[TTS_CANCEL] turn_id=${this._turnId} AudioContext_failed: ${e.message}`);
        _diag.lastTtsError = `AudioContext: ${e.message}`;
        this._playing = false;
        _diag.currentlyPlaying = false;
        return;
      }
    }

    while (this._audioQueue.length > 0 && !this._cancelled) {
      _diag.pendingChunks = this._audioQueue.length;
      const bufPromise = this._audioQueue.shift();
      _diag.queueSize = this._audioQueue.length;

      // Check turn is still active before awaiting synthesis
      if (this._cancelled) {
        console.info(`[TTS_STALE_CHUNK_DROPPED] turn_id=${this._turnId} reason=cancelled_before_decode`);
        break;
      }

      let buf;
      try {
        buf = await bufPromise;
      } catch {
        continue;
      }
      if (!buf || this._cancelled) {
        if (this._cancelled) {
          console.info(`[TTS_STALE_CHUNK_DROPPED] turn_id=${this._turnId} reason=cancelled_after_synthesis`);
        }
        continue;
      }

      let decoded;
      try {
        decoded = await this._ctx.decodeAudioData(buf);
      } catch (e) {
        console.warn(`[TTS_CANCEL] turn_id=${this._turnId} decodeAudioData_failed: ${e.message}`);
        continue;
      }
      if (this._cancelled) break;

      // First audio ready — record latency and signal speaking
      if (this._latency.firstAudioMs === null) {
        this._latency.firstAudioMs = Date.now() - this._t0;
        console.info(
          `[TTS_PLAY_START] turn_id=${this._turnId} first_audio_ms=${this._latency.firstAudioMs} first_sentence_ms=${this._latency.firstSentenceMs}`
        );
        this._onLatency({
          firstSentenceMs: this._latency.firstSentenceMs,
          firstAudioMs: this._latency.firstAudioMs,
        });
      }

      this._onSpeakingChange(true);
      _pushDiag();

      await new Promise((resolve) => {
        const src = this._ctx.createBufferSource();
        this._currentSrc = src;
        src.buffer = decoded;
        src.connect(this._ctx.destination);
        src.onended = () => {
          this._currentSrc = null;
          resolve();
        };
        src.start();
      });

      if (this._cancelled) break;
    }

    this._stopBargeIn();
    this._playing = false;
    _diag.currentlyPlaying = false;
    _diag.pendingChunks = 0;

    if (!this._cancelled) {
      console.info(`[TTS_PLAY_END] turn_id=${this._turnId} total_sentences=${this._latency.totalSentences}`);
      if (this._ctx) {
        this._ctx.close().catch(() => {});
        this._ctx = null;
      }
      _diag.activeTurnId = null;
      _pushDiag();
      this._onSpeakingChange(false);
    }
  }

  _stopBargeIn() {
    if (this._bargeCleanup) {
      this._bargeCleanup();
      this._bargeCleanup = null;
    }
  }
}
