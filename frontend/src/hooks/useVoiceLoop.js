/**
 * useVoiceLoop — Hands-free voice pipeline hook.
 *
 * Full autonomous loop:
 *   wake word → auto-record (VAD-gated) → transcribe → chat stream → TTS → play → listen
 *
 * The hook owns the WebSocket connection to the wake word endpoint and the
 * microphone recording session. All message management is delegated to the
 * parent via onSubmit — which should be the same submitQuery used for typed input.
 *
 * States:
 *   idle       — not running
 *   listening  — connected to wake WS, waiting for "hey_silvia"
 *   recording  — capturing microphone audio (VAD-gated stop)
 *   processing — transcribing + chat + TTS pipeline
 *   error      — unrecoverable failure; call startLoop() to retry
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeAudio, getWakeWsUrl } from "../lib/api";

export const LOOP_STATE = {
  IDLE: "idle",
  LISTENING: "listening",
  RECORDING: "recording",
  PROCESSING: "processing",
  ERROR: "error",
};

// VAD constants
const SILENCE_THRESHOLD = 0.013;   // RMS below this = silence
const SILENCE_AFTER_SPEECH_MS = 1800; // Stop after 1.8 s of post-speech silence
const MAX_RECORD_MS = 14000;       // Hard cap — don't record forever

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export function useVoiceLoop({
  sessionId,
  onSubmit,       // async (text, opts) => void  — same as typed submitQuery
  isSpeaking,     // bool — current TTS playback state from parent
  enabled = false,
}) {
  const [loopState, setLoopState] = useState(LOOP_STATE.IDLE);
  const [loopError, setLoopError] = useState(null);

  // Refs so async callbacks always see current values without stale closures
  const activeRef = useRef(false);
  const isSpeakingRef = useRef(isSpeaking);
  const wsRef = useRef(null);
  const streamRef = useRef(null);

  // Keep refs in sync with latest props
  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

  const onSubmitRef = useRef(onSubmit);
  useEffect(() => { onSubmitRef.current = onSubmit; }, [onSubmit]);

  // ── Mic access ──────────────────────────────────────────────────────────────

  async function acquireMic() {
    if (streamRef.current) return streamRef.current; // already held
    streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    return streamRef.current;
  }

  function releaseMic() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  // ── VAD-gated recording ─────────────────────────────────────────────────────

  async function recordUntilSilence(micStream) {
    const chunks = [];

    // AudioContext for RMS silence detection
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(micStream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    const recorder = new MediaRecorder(micStream);
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
    recorder.start(100);

    // VAD loop — resolves on silence-after-speech or hard timeout
    await new Promise((resolve) => {
      const data = new Float32Array(analyser.fftSize);
      let heardSpeech = false;
      let silenceStart = null;
      const hardStop = setTimeout(() => resolve("timeout"), MAX_RECORD_MS);
      let raf;

      function tick() {
        if (!activeRef.current) { resolve("cancelled"); return; }
        analyser.getFloatTimeDomainData(data);
        const rms = Math.sqrt(data.reduce((s, v) => s + v * v, 0) / data.length);

        if (rms >= SILENCE_THRESHOLD) {
          heardSpeech = true;
          silenceStart = null;
        } else if (heardSpeech) {
          if (!silenceStart) silenceStart = Date.now();
          else if (Date.now() - silenceStart >= SILENCE_AFTER_SPEECH_MS) {
            clearTimeout(hardStop);
            resolve("silence");
            return;
          }
        }
        raf = requestAnimationFrame(tick);
      }
      tick();
    });

    // Stop recorder and collect final chunk
    await new Promise((resolve) => {
      recorder.onstop = resolve;
      if (recorder.state !== "inactive") recorder.stop();
    });
    ctx.close().catch(() => {});

    if (chunks.length === 0) return null;
    return new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
  }

  // ── Single pipeline cycle ───────────────────────────────────────────────────

  async function runCycle(micStream) {
    if (!activeRef.current) return;
    setLoopState(LOOP_STATE.RECORDING);

    const audioBlob = await recordUntilSilence(micStream);
    if (!audioBlob || !activeRef.current) return;

    setLoopState(LOOP_STATE.PROCESSING);

    // Transcribe
    let transcript = "";
    try {
      const result = await transcribeAudio(audioBlob, audioBlob.type);
      transcript = result?.text?.trim() ?? "";
    } catch {
      // STT failure — silently skip this cycle
      return;
    }
    if (!transcript || !activeRef.current) return;

    // Submit through the normal chat pipeline (handles messages + TTS)
    try {
      await onSubmitRef.current(transcript, { voice: true });
    } catch {
      // Chat failure — non-fatal
    }
    if (!activeRef.current) return;

    // Wait for TTS playback to complete before returning to listening.
    // Give it up to 500 ms to start, then wait for it to finish (max 60 s).
    const waitStart = Date.now();
    while (!isSpeakingRef.current && Date.now() - waitStart < 600) {
      await sleep(80);
    }
    const speakStart = Date.now();
    while (isSpeakingRef.current && Date.now() - speakStart < 60_000) {
      await sleep(200);
    }
  }

  // ── Wake word connection ────────────────────────────────────────────────────

  function connectWake(micStream) {
    if (!activeRef.current) return;
    setLoopState(LOOP_STATE.LISTENING);

    const ws = new WebSocket(getWakeWsUrl());
    wsRef.current = ws;

    ws.onmessage = async (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.event !== "wake_word_detected") return;

      ws.close();
      wsRef.current = null;

      await runCycle(micStream);

      // After cycle, reconnect for next wake event
      if (activeRef.current) connectWake(micStream);
    };

    ws.onerror = () => {
      if (!activeRef.current) return;
      setLoopError("Wake word connection failed — check that the backend is running.");
      setLoopState(LOOP_STATE.ERROR);
    };

    // Reconnect on unexpected close (not triggered by us)
    ws.onclose = (e) => {
      if (!activeRef.current || e.code === 1000) return;
      setTimeout(() => {
        if (activeRef.current) connectWake(micStream);
      }, 2000);
    };
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  const startLoop = useCallback(async () => {
    if (activeRef.current) return;
    activeRef.current = true;
    setLoopError(null);
    setLoopState(LOOP_STATE.LISTENING);

    let micStream;
    try {
      micStream = await acquireMic();
    } catch {
      setLoopError("Microphone access denied. Grant permission and try again.");
      setLoopState(LOOP_STATE.ERROR);
      activeRef.current = false;
      return;
    }

    connectWake(micStream);
  }, []);

  const stopLoop = useCallback(() => {
    activeRef.current = false;
    wsRef.current?.close();
    wsRef.current = null;
    releaseMic();
    setLoopState(LOOP_STATE.IDLE);
    setLoopError(null);
  }, []);

  // Respond to enabled prop
  useEffect(() => {
    if (enabled) {
      startLoop();
    } else {
      stopLoop();
    }
    return stopLoop;
  }, [enabled, startLoop, stopLoop]);

  return { loopState, loopError, startLoop, stopLoop };
}
