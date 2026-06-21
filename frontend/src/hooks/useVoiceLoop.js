/**
 * useVoiceLoop — Hardened hands-free voice pipeline.
 *
 * States:
 *   idle           — not running
 *   listening      — connected to wake WS, waiting for "hey silvia"
 *   wake_detected  — wake event received, evaluating
 *   armed          — confirmation window open (2s to speak a command)
 *   recording      — capturing microphone audio (VAD-gated stop)
 *   processing     — transcribing + chat + TTS pipeline
 *   cooldown       — ignoring wake triggers after response/false activation
 *   error          — unrecoverable failure
 *
 * Hardening:
 *   - Backend sends confidence with every wake event; only accepted=true triggers
 *   - Armed state: 2s window requiring follow-up speech before recording
 *   - Command validation: rejects transcripts < WAKE_MIN_COMMAND_WORDS (except known short commands)
 *   - Cooldown: ignores wake triggers for WAKE_WORD_COOLDOWN_SECONDS after each cycle
 *   - False activation reporting: POST /api/voice/wake/false-activation
 *   - System audio ignored via microphone-only input (no loopback)
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
  COOLDOWN: "cooldown",
  ERROR: "error",
};

const SILENCE_THRESHOLD = 0.013;
const SILENCE_AFTER_SPEECH_MS = 1800;
const MAX_RECORD_MS = 14000;
const ARM_WINDOW_MS = 2000;
const COOLDOWN_MS = 5000;
const FOLLOWUP_WINDOW_MS = 15000;
const MIN_COMMAND_WORDS = 3;

const SHORT_COMMANDS = new Set([
  "stop", "cancel", "pause", "resume", "yes", "no", "mute", "unmute",
  "help", "hey", "silvia", "listen", "go", "okay",
]);

const CONFIRM_WORDS = new Set([
  "yes", "yeah", "yep", "silvia", "go", "go ahead", "listen", "okay", "ok",
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
}) {
  const [loopState, setLoopState] = useState(LOOP_STATE.IDLE);
  const [loopError, setLoopError] = useState(null);

  const activeRef = useRef(false);
  const isSpeakingRef = useRef(isSpeaking);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const cooldownTimerRef = useRef(null);
  const lastSuccessfulCycleRef = useRef(0);
  const followupTimerRef = useRef(null);

  useEffect(() => { isSpeakingRef.current = isSpeaking; }, [isSpeaking]);

  const onSubmitRef = useRef(onSubmit);
  useEffect(() => { onSubmitRef.current = onSubmit; }, [onSubmit]);

  async function acquireMic() {
    if (streamRef.current) return streamRef.current;
    streamRef.current = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    return streamRef.current;
  }

  function releaseMic() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  function enterCooldown(wasSuccessful = false) {
    setLoopState(LOOP_STATE.COOLDOWN);
    if (cooldownTimerRef.current) clearTimeout(cooldownTimerRef.current);
    if (wasSuccessful) {
      lastSuccessfulCycleRef.current = Date.now();
    }
    cooldownTimerRef.current = setTimeout(() => {
      if (activeRef.current) setLoopState(LOOP_STATE.LISTENING);
    }, COOLDOWN_MS);
  }

  function inFollowupWindow() {
    return lastSuccessfulCycleRef.current > 0 &&
      (Date.now() - lastSuccessfulCycleRef.current) < FOLLOWUP_WINDOW_MS;
  }

  function validateCommand(transcript) {
    const words = transcript.trim().split(/\s+/);
    if (words.length === 0) return { valid: false, reason: "empty transcript" };

    if (words.length === 1 && SHORT_COMMANDS.has(words[0].toLowerCase())) {
      return { valid: true };
    }

    if (words.length < MIN_COMMAND_WORDS) {
      return {
        valid: false,
        reason: `too short (${words.length} words, need ${MIN_COMMAND_WORDS}+)`,
      };
    }

    return { valid: true };
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
      if (rms >= SILENCE_THRESHOLD * 1.5) {
        detected = true;
        break;
      }
      await sleep(50);
    }

    ctx.close().catch(() => {});
    return detected;
  }

  async function runCycle(micStream) {
    if (!activeRef.current) return;

    setLoopState(LOOP_STATE.ARMED);

    const speechStarted = await waitForSpeechStart(micStream, ARM_WINDOW_MS);
    if (!speechStarted || !activeRef.current) {
      reportFalseActivation();
      enterCooldown();
      return;
    }

    setLoopState(LOOP_STATE.RECORDING);

    const audioBlob = await recordUntilSilence(micStream);
    if (!audioBlob || !activeRef.current) {
      enterCooldown();
      return;
    }

    setLoopState(LOOP_STATE.PROCESSING);

    let transcript = "";
    try {
      const result = await transcribeAudio(audioBlob, audioBlob.type);
      transcript = result?.text?.trim() ?? "";
    } catch {
      enterCooldown();
      return;
    }

    if (!transcript || !activeRef.current) {
      reportFalseActivation();
      enterCooldown();
      return;
    }

    const validation = validateCommand(transcript);
    if (!validation.valid) {
      reportFalseActivation();
      enterCooldown();
      return;
    }

    try {
      await onSubmitRef.current(transcript, { voice: true });
    } catch {
      // non-fatal
    }

    if (!activeRef.current) return;

    const waitStart = Date.now();
    while (!isSpeakingRef.current && Date.now() - waitStart < 600) {
      await sleep(80);
    }
    const speakStart = Date.now();
    while (isSpeakingRef.current && Date.now() - speakStart < 60_000) {
      await sleep(200);
    }

    enterCooldown(true);
  }

  async function followupCycle(micStream) {
    if (!activeRef.current || !inFollowupWindow()) return false;
    const speechStarted = await waitForSpeechStart(micStream, FOLLOWUP_WINDOW_MS);
    if (!speechStarted || !activeRef.current) return false;
    if (!inFollowupWindow()) return false;
    await runCycle(micStream);
    return true;
  }

  function connectWake(micStream) {
    if (!activeRef.current) return;

    // Follow-up window: if we just had a successful cycle, listen for
    // follow-up speech without requiring a wake word.
    if (inFollowupWindow()) {
      setLoopState(LOOP_STATE.LISTENING);
      (async () => {
        const followed = await followupCycle(micStream);
        if (activeRef.current) connectWake(micStream);
      })();
      return;
    }

    setLoopState(LOOP_STATE.LISTENING);

    const ws = new WebSocket(getWakeWsUrl());
    wsRef.current = ws;

    ws.onmessage = async (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }

      if (!msg.wake) return;
      if (!msg.accepted) return;

      setLoopState(LOOP_STATE.WAKE_DETECTED);

      ws.close();
      wsRef.current = null;

      await runCycle(micStream);

      if (activeRef.current) connectWake(micStream);
    };

    ws.onerror = () => {
      if (!activeRef.current) return;
      setLoopError("Wake word connection failed — check that the backend is running.");
      setLoopState(LOOP_STATE.ERROR);
    };

    ws.onclose = (e) => {
      if (!activeRef.current || e.code === 1000) return;
      setTimeout(() => {
        if (activeRef.current) connectWake(micStream);
      }, 2000);
    };
  }

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
    if (cooldownTimerRef.current) clearTimeout(cooldownTimerRef.current);
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
