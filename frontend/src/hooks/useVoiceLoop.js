/**
 * useVoiceLoop — Real conversational voice pipeline.
 *
 * State machine:
 *   idle               — loop not running
 *   listening          — wake word WebSocket active ("hey silvia")
 *   wake_detected      — wake event received, about to arm
 *   armed              — 2s window to confirm intentional speech (initial only)
 *   recording          — capturing mic audio (VAD-gated stop)
 *   processing         — transcribing + submitting to chat
 *   speaking           — TTS audio is playing
 *   conversation_active — after speaking, waiting for follow-up (no wake word)
 *   listening_again    — follow-up speech detected, recording it
 *   cooldown           — brief pause (only after followup timeout, not after speaking)
 *   error              — unrecoverable failure
 *
 * Key design rules:
 *   - COOLDOWN never blocks follow-up conversation. It only fires when the
 *     follow-up timeout expires (user didn't reply in time).
 *   - Follow-up path skips the ARM window — short replies ("yes", "no", "ok")
 *     must not be lost to a second VAD gate.
 *   - speaking state is set AFTER synthesis completes (audio is ready to play),
 *     so the voice loop is not frozen during TTS synthesis.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeAudio, getWakeWsUrl } from "../lib/api";

export const LOOP_STATE = {
  IDLE: "idle",
  LISTENING: "listening",
  WAKE_DETECTED: "wake_detected",
  ARMED: "armed",
  RECORDING: "recording",
  PROCESSING: "processing",
  SPEAKING: "speaking",
  CONVERSATION_ACTIVE: "conversation_active",
  LISTENING_AGAIN: "listening_again",
  COOLDOWN: "cooldown",
  ERROR: "error",
};

const SILENCE_THRESHOLD = 0.013;
const SILENCE_AFTER_SPEECH_MS = 1800;
const MAX_RECORD_MS = 14000;
const ARM_WINDOW_MS = 2000;
const COOLDOWN_MS = 1000;
const MIN_COMMAND_WORDS = 2;  // lowered from 3 — "yes"/"no" are valid follow-ups

const SHORT_COMMANDS = new Set([
  "stop", "cancel", "pause", "resume", "yes", "no", "mute", "unmute",
  "help", "hey", "silvia", "listen", "go", "okay", "sure", "open", "launch",
]);

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

const _host = window.location.hostname;

function reportFalseActivation() {
  fetch(`http://${_host}:8001/api/voice/wake/false-activation`, { method: "POST" }).catch(() => {});
}

export function useVoiceLoop({
  sessionId,
  onSubmit,
  isSpeaking,
  enabled = false,
  mode = "stt_only",
  conversationTimeoutMs = 10000,
  autoSpeakEnabled = true,
}) {
  const [loopState, setLoopState] = useState(LOOP_STATE.IDLE);
  const [loopError, setLoopError] = useState(null);

  const activeRef = useRef(false);
  const isSpeakingRef = useRef(isSpeaking);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const conversationTimeoutMsRef = useRef(conversationTimeoutMs);
  const autoSpeakEnabledRef = useRef(autoSpeakEnabled);
  const modeRef = useRef(mode);

  useEffect(() => { isSpeakingRef.current = isSpeaking; }, [isSpeaking]);
  useEffect(() => { conversationTimeoutMsRef.current = conversationTimeoutMs; }, [conversationTimeoutMs]);
  useEffect(() => { autoSpeakEnabledRef.current = autoSpeakEnabled; }, [autoSpeakEnabled]);
  useEffect(() => { modeRef.current = mode; }, [mode]);

  const onSubmitRef = useRef(onSubmit);
  useEffect(() => { onSubmitRef.current = onSubmit; }, [onSubmit]);

  // ── Mic management ────────────────────────────────────────────────────────

  async function acquireMic() {
    if (streamRef.current) return streamRef.current;
    streamRef.current = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    return streamRef.current;
  }

  function releaseMic() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  // ── VAD helpers ───────────────────────────────────────────────────────────

  async function waitForSpeechStart(micStream, timeoutMs) {
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(micStream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    const data = new Float32Array(analyser.fftSize);

    const started = Date.now();
    let detected = false;
    while (Date.now() - started < timeoutMs) {
      if (!activeRef.current) break;
      analyser.getFloatTimeDomainData(data);
      const rms = Math.sqrt(data.reduce((s, v) => s + v * v, 0) / data.length);
      if (rms >= SILENCE_THRESHOLD * 1.5) { detected = true; break; }
      await sleep(50);
    }
    ctx.close().catch(() => {});
    return detected;
  }

  async function recordUntilSilence(micStream) {
    const chunks = [];
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(micStream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    const recorder = new MediaRecorder(micStream);
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
    recorder.start(100);

    await new Promise((resolve) => {
      const data = new Float32Array(analyser.fftSize);
      let heardSpeech = false;
      let silenceStart = null;
      const hardStop = setTimeout(() => resolve("timeout"), MAX_RECORD_MS);

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
        requestAnimationFrame(tick);
      }
      tick();
    });

    await new Promise((resolve) => {
      recorder.onstop = resolve;
      if (recorder.state !== "inactive") recorder.stop();
    });
    ctx.close().catch(() => {});
    if (chunks.length === 0) return null;
    return new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
  }

  // ── Core conversation cycle ───────────────────────────────────────────────
  //
  // captureAndSubmit: records speech, transcribes, submits, waits for TTS to
  // finish. Does NOT include an ARM window — callers decide whether to ARM first.
  //
  // Returns true if a successful command was processed and TTS finished.

  async function captureAndSubmit(micStream) {
    if (!activeRef.current) return false;

    setLoopState(LOOP_STATE.RECORDING);
    const audioBlob = await recordUntilSilence(micStream);
    if (!audioBlob || !activeRef.current) return false;

    setLoopState(LOOP_STATE.PROCESSING);
    let transcript = "";
    try {
      const result = await transcribeAudio(audioBlob, audioBlob.type);
      transcript = result?.text?.trim() ?? "";
    } catch {
      return false;
    }

    if (!transcript || !activeRef.current) {
      reportFalseActivation();
      return false;
    }

    // Allow short follow-up commands ("yes", "no", single word)
    const words = transcript.trim().split(/\s+/);
    const isShort = words.length === 1 && SHORT_COMMANDS.has(words[0].toLowerCase());
    if (!isShort && words.length < MIN_COMMAND_WORDS) {
      reportFalseActivation();
      return false;
    }

    try {
      await onSubmitRef.current(transcript, { voice: true });
    } catch {}

    if (!activeRef.current) return false;

    // Wait for speaking to become true — synthesis happens in useCommandCenterData.
    // speaking: true is set AFTER synthesis, so this wait is for audio ready + playing.
    // 8s timeout matches the TTS synthesis timeout in useCommandCenterData.
    const speakWaitMs = autoSpeakEnabledRef.current ? 8000 : 600;
    const waitStart = Date.now();
    while (!isSpeakingRef.current && Date.now() - waitStart < speakWaitMs) {
      if (!activeRef.current) return false;
      await sleep(80);
    }

    if (isSpeakingRef.current) {
      setLoopState(LOOP_STATE.SPEAKING);
      // Wait for playback to finish (no timeout — let audio complete naturally)
      while (isSpeakingRef.current && activeRef.current) {
        await sleep(150);
      }
    }

    return true;
  }

  // ── Wake word listener ────────────────────────────────────────────────────
  //
  // Returns a promise that resolves when:
  //   true  — wake word confirmed
  //   false — loop stopped or WS error

  function awaitWakeWord(micStream) {
    return new Promise((resolve) => {
      if (!activeRef.current) { resolve(false); return; }

      const ws = new WebSocket(getWakeWsUrl());
      wsRef.current = ws;

      // Pipe mic → int16 → WebSocket
      let audioCtx = null;
      let processor = null;

      ws.onopen = () => {
        try {
          audioCtx = new AudioContext({ sampleRate: 16000 });
          const source = audioCtx.createMediaStreamSource(micStream);
          processor = audioCtx.createScriptProcessor(1024, 1, 1);
          processor.onaudioprocess = (e) => {
            if (ws.readyState !== WebSocket.OPEN) return;
            const float32 = e.inputBuffer.getChannelData(0);
            const int16 = new Int16Array(float32.length);
            for (let i = 0; i < float32.length; i++) {
              int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)));
            }
            ws.send(int16.buffer);
          };
          source.connect(processor);
          processor.connect(audioCtx.destination);
        } catch {}
      };

      function cleanup(result) {
        if (processor) { try { processor.disconnect(); } catch {} processor = null; }
        if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null; }
        if (ws.readyState < WebSocket.CLOSING) ws.close(1000);
        wsRef.current = null;
        resolve(result);
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.wake && msg.accepted) cleanup(true);
        } catch {}
      };

      ws.onerror = () => cleanup(false);

      // Always resolve on close — regardless of code or who closed it.
      // If cleanup(true) already ran (wake accepted), the second resolve(false)
      // is a no-op (Promise resolves only once). Without this, stopLoop() closes
      // the WS with code 1000 and the Promise hangs forever, preventing the loop
      // from restarting cleanly on next enable.
      ws.onclose = () => cleanup(false);
    });
  }

  // ── STABLE simple loop (STT-only / wake_word) ─────────────────────────────
  //
  // Wake word detected → record one utterance → transcribe → send to chat.
  // The mic only stays open for a follow-up when SILVIA's reply expects an
  // answer (a question or a request/confirmation). Otherwise it returns to
  // wake-word-only listening — it does NOT keep capturing your speech.
  // No ARM window, no auto-TTS, no speaking wait.

  async function captureTranscribeSubmit(micStream) {
    // Returns the submit result ({ expectsReply }) or null if nothing was sent.
    setLoopState(LOOP_STATE.RECORDING);
    const audioBlob = await recordUntilSilence(micStream);
    if (!audioBlob || !activeRef.current) return null;

    setLoopState(LOOP_STATE.PROCESSING);
    let transcript = "";
    try {
      const result = await transcribeAudio(audioBlob, audioBlob.type);
      transcript = result?.text?.trim() ?? "";
    } catch {
      return null;
    }
    if (!transcript) { reportFalseActivation(); return null; }

    const words = transcript.trim().split(/\s+/);
    const isShort = words.length === 1 && SHORT_COMMANDS.has(words[0].toLowerCase());
    if (!isShort && words.length < MIN_COMMAND_WORDS) { reportFalseActivation(); return null; }

    try {
      // voice:true so the backend intent-classifies expects_reply for this turn.
      // TTS stays off — auto-speech is gated to presence_experimental mode.
      return await onSubmitRef.current(transcript, { voice: true });
    } catch {
      return null;
    }
  }

  async function runSimpleLoop(micStream) {
    while (activeRef.current) {
      setLoopState(LOOP_STATE.LISTENING);

      const woke = await awaitWakeWord(micStream);
      if (!woke) {
        if (!activeRef.current) break;
        await sleep(2000); // unexpected WS close — reconnect
        continue;
      }
      if (!activeRef.current) break;

      // First turn is wake-triggered. Subsequent turns happen only while
      // SILVIA keeps asking the user something (conditional follow-up).
      let keepCapturing = true;
      while (keepCapturing && activeRef.current) {
        const res = await captureTranscribeSubmit(micStream);
        if (!res?.expectsReply || !activeRef.current) {
          break; // no question asked (or nothing sent) → back to wake word
        }

        // SILVIA asked something — open ONE follow-up window, no wake word.
        // If the user starts speaking, capture their answer; if they stay
        // silent past the timeout, drop back to wake-word-only listening.
        setLoopState(LOOP_STATE.CONVERSATION_ACTIVE);
        const spoke = await waitForSpeechStart(micStream, conversationTimeoutMsRef.current);
        if (!spoke) break;
      }
    }
  }

  // ── Conversational loop (presence_experimental ONLY — disabled by default) ──

  async function runConversationLoop(micStream) {
    while (activeRef.current) {
      // ── WAKE WORD PHASE ───────────────────────────────────────────────────
      setLoopState(LOOP_STATE.LISTENING);

      const woke = await awaitWakeWord(micStream);
      if (!woke) {
        if (!activeRef.current) break;
        // Reconnect after unexpected close
        await sleep(2000);
        continue;
      }

      setLoopState(LOOP_STATE.WAKE_DETECTED);

      // ARM: 2s window to confirm intentional speech (initial wake only)
      const armed = await waitForSpeechStart(micStream, ARM_WINDOW_MS);
      if (!armed || !activeRef.current) {
        reportFalseActivation();
        setLoopState(LOOP_STATE.COOLDOWN);
        await sleep(COOLDOWN_MS);
        continue;
      }

      // ── CONVERSATION PHASE ────────────────────────────────────────────────
      // First cycle
      const firstOk = await captureAndSubmit(micStream);
      if (!firstOk || !activeRef.current) {
        setLoopState(LOOP_STATE.COOLDOWN);
        await sleep(COOLDOWN_MS);
        continue;
      }

      // Follow-up loop — no wake word, no ARM window for replies
      while (activeRef.current) {
        // Immediately open mic for follow-up (no cooldown here!)
        setLoopState(LOOP_STATE.CONVERSATION_ACTIVE);
        const followupDetected = await waitForSpeechStart(
          micStream, conversationTimeoutMsRef.current
        );

        if (!followupDetected || !activeRef.current) {
          // Timeout — conversation naturally ended
          break;
        }

        // User spoke — go straight to recording (skip ARM)
        setLoopState(LOOP_STATE.LISTENING_AGAIN);
        const followupOk = await captureAndSubmit(micStream);
        if (!followupOk || !activeRef.current) break;
        // Successful follow-up — loop back to CONVERSATION_ACTIVE
      }

      // Conversation done — brief cooldown before returning to wake word
      if (activeRef.current) {
        setLoopState(LOOP_STATE.COOLDOWN);
        await sleep(COOLDOWN_MS);
      }
    }
  }

  // ── Start / Stop ──────────────────────────────────────────────────────────

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

    // Stable default uses the simple STT-only loop. The conversational loop
    // (auto TTS, follow-up, barge-in) runs ONLY in presence_experimental.
    const loop = modeRef.current === "presence_experimental" ? runConversationLoop : runSimpleLoop;
    loop(micStream).catch((err) => {
      if (activeRef.current) {
        setLoopError(err.message || "Voice loop crashed.");
        setLoopState(LOOP_STATE.ERROR);
      }
    }).finally(() => {
      activeRef.current = false;
    });
  }, []);

  const stopLoop = useCallback(() => {
    activeRef.current = false;
    if (wsRef.current) { wsRef.current.close(1000); wsRef.current = null; }
    releaseMic();
    setLoopState(LOOP_STATE.IDLE);
    setLoopError(null);
  }, []);

  useEffect(() => {
    if (enabled) startLoop();
    else stopLoop();
    return stopLoop;
  }, [enabled, startLoop, stopLoop]);

  return { loopState, loopError, startLoop, stopLoop };
}
