import { useCallback, useEffect, useRef, useState } from "react";
import { useVoiceLoop } from "./useVoiceLoop";
import { SentenceStreamTTS } from "../voice/SentenceStreamTTS";

import {
  clearHistory,
  createEventsSocket,
  createNode,
  deleteNode,
  dismissWatchAlert,
  executeActionAlias,
  fetchActions,
  fetchAudioState,
  fetchDevices,
  fetchHistory,
  fetchLogs,
  fetchMode,
  fetchNodes,
  fetchVoiceStatus,
  fetchWatchAlerts,
  mediaNext,
  mediaPlayPause,
  mediaPrevious,
  openAppAction,
  probeNode,
  verifyNode,
  sendChatStream,
  sendDecision,
  setAudioVolume,
  setMode,
  synthesizeSpeech,
  toggleMute,
  updateNode,
  updateVoiceState,
  volumeDown,
  volumeUp,
} from "../lib/api";

// STABLE STT-only defaults — auto TTS / conversation / barge-in are OFF.
// These conversational features only take effect in presence_experimental mode.
const DEFAULT_VOICE_SETTINGS = {
  autoSpeak: false,
  continuousConversation: false,
  bargeIn: false,
  wakeWordEnabled: true,
  conversationTimeoutMs: 8000,
};

// Supported voice modes. Stable default is "stt_only".
// presence_experimental = old conversational pipeline (disabled by default).
const VOICE_MODES = ["off", "stt_only", "push_to_talk", "wake_word", "presence_experimental"];
const DEFAULT_VOICE_MODE = "stt_only";

function loadVoiceMode() {
  try {
    const m = localStorage.getItem("silvia_voice_mode");
    return VOICE_MODES.includes(m) ? m : DEFAULT_VOICE_MODE;
  } catch {
    return DEFAULT_VOICE_MODE;
  }
}

export function useCommandCenterData() {
  const [mode, setModeState] = useState("conversation");
  const [modeReason, setModeReason] = useState("Loading");
  const [voice, setVoice] = useState(null);
  const [audio, setAudio] = useState(null);
  const [devices, setDevices] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [watchAlerts, setWatchAlerts] = useState([]);
  const [liveTelemetryPoints, setLiveTelemetryPoints] = useState({});
  const [actions, setActions] = useState([]);
  const [draft, setDraft] = useState("");
  const [sessionId] = useState("default-session");
  const [messages, setMessages] = useState([]);
  // Keep messagesRef in sync so submitQuery can read current messages without capturing stale closure
  useEffect(() => { messagesRef.current = messages; }, [messages]);
  const [logs, setLogs] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const socketRef = useRef(null);

  // Voice settings — persisted in localStorage
  const [voiceSettings, _setVoiceSettings] = useState(() => {
    try {
      return { ...DEFAULT_VOICE_SETTINGS, ...JSON.parse(localStorage.getItem("silvia_voice_settings") || "{}") };
    } catch {
      return { ...DEFAULT_VOICE_SETTINGS };
    }
  });
  const voiceSettingsRef = useRef(voiceSettings);
  useEffect(() => { voiceSettingsRef.current = voiceSettings; }, [voiceSettings]);

  function updateVoiceSetting(key, value) {
    _setVoiceSettings((s) => {
      const next = { ...s, [key]: value };
      localStorage.setItem("silvia_voice_settings", JSON.stringify(next));
      return next;
    });
  }

  // Centralized TTS state
  const ttsCtxRef = useRef(null);
  const ttsSrcRef = useRef(null);
  const ttsBargeCleanupRef = useRef(null);
  // Active SentenceStreamTTS instance (streaming path) — cancelled by stopSpeaking()
  const streamTTSRef = useRef(null);
  // Track which message IDs have been spoken — ref avoids triggering re-renders (which would self-cancel speak())
  const ttsSpokenIdsRef = useRef(new Set());
  // Mirror of messages state — lets submitQuery read current messages without a closure/dependency
  const messagesRef = useRef([]);

  function stopSpeaking() {
    // Cancel any sentence-streaming TTS (the fast path)
    if (streamTTSRef.current) { streamTTSRef.current.cancel(); streamTTSRef.current = null; }
    // Cancel any post-done TTS (the fallback path)
    if (ttsBargeCleanupRef.current) { ttsBargeCleanupRef.current(); ttsBargeCleanupRef.current = null; }
    if (ttsSrcRef.current) { try { ttsSrcRef.current.stop(); } catch {} ttsSrcRef.current = null; }
    if (ttsCtxRef.current) { ttsCtxRef.current.close().catch(() => {}); ttsCtxRef.current = null; }
    setVoice((v) => (v ? { ...v, speaking: false } : v));
    updateVoiceState({ speaking: false }).catch(() => {});
  }

  // Voice mode — single source of truth for how voice behaves. STABLE default
  // is "stt_only". presence_experimental re-enables the old conversational loop.
  const [voiceMode, _setVoiceMode] = useState(loadVoiceMode);
  const voiceModeRef = useRef(voiceMode);
  useEffect(() => { voiceModeRef.current = voiceMode; }, [voiceMode]);

  // Voice loop — persisted so the user's choice survives page refresh
  const [voiceLoopEnabled, setVoiceLoopEnabled] = useState(() => {
    try { return localStorage.getItem("silvia_voice_loop_enabled") !== "false"; } catch { return true; }
  });
  const submitQueryRef = useRef(null);
  const stableSubmit = useCallback((...args) => submitQueryRef.current?.(...args), []);

  // The wake-word loop only runs for listening modes (stt_only / wake_word /
  // presence_experimental). "off" and "push_to_talk" never auto-listen.
  const loopActiveModes = ["stt_only", "wake_word", "presence_experimental"];
  const loopEnabled = voiceLoopEnabled && loopActiveModes.includes(voiceMode);

  const { loopState: voiceLoopState, loopError: voiceLoopError } = useVoiceLoop({
    sessionId,
    onSubmit: stableSubmit,
    isSpeaking: voice?.speaking ?? false,
    enabled: loopEnabled,
    mode: voiceMode,
    conversationTimeoutMs: voiceSettings.conversationTimeoutMs,
    autoSpeakEnabled: voiceSettings.autoSpeak,
  });

  // ── Startup cleanup ─────────────────────────────────────────────────────────
  // On mount, cancel any lingering TTS playback / queues and reset voice output
  // state to a clean idle. Guarantees no stale audio survives a page reload.
  useEffect(() => {
    stopSpeaking();
    ttsSpokenIdsRef.current = new Set();
    updateVoiceState({ speaking: false, speech_enabled: false }).catch(() => {});
    console.info(`[VOICE_INIT] mode=${voiceModeRef.current} auto_tts=false followup=false presence=${voiceModeRef.current === "presence_experimental"}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const [modeData, voiceData, deviceData, actionData, logData, audioData, historyData, nodesData, watchData] =
          await Promise.all([
            fetchMode(),
            fetchVoiceStatus(),
            fetchDevices(),
            fetchActions(),
            fetchLogs(),
            fetchAudioState(),
            fetchHistory(sessionId, 100),
            fetchNodes(),
            fetchWatchAlerts(),
          ]);

        setModeState(modeData.active_mode);
        setModeReason(modeData.reason);
        setVoice(voiceData);
        setDevices(deviceData);
        setActions(actionData);
        setLogs(logData);
        setAudio(audioData);
        setNodes(nodesData);
        setWatchAlerts(watchData);

        if (historyData.messages && historyData.messages.length > 0) {
          const restored = historyData.messages.map((msg, i) => ({
            id: `history-${i}`,
            role: msg.role,
            mode: msg.mode || "conversation",
            answer: msg.content,
            title: msg.role === "assistant" ? "SILVIA" : undefined,
            processing_time_ms: 0,
            sources: [],
            agents: [],
            logs: [],
            payload: {},
            isHistory: true,
          }));
          setMessages(restored);
        } else {
          setMessages([{
            id: "welcome",
            role: "assistant",
            mode: "conversation",
            title: "SILVIA Online",
            answer: "SILVIA is live — AI Operating System initialised. Conversation history persisted across sessions.\n\nSay 'brief me' for a mission status, 'open [app]' to launch something, or ask anything.",
            processing_time_ms: 0,
            sources: [],
            agents: [],
            logs: [],
            payload: {},
          }]);
        }
      } catch (loadError) {
        setError(loadError.message || "Failed to load command center data.");
      }
    }

    load();
  }, [sessionId]);

  useEffect(() => {
    let dead = false;
    let backoff = 1000;
    let reconnectTimer = null;
    let activeSocket = null;

    function connect() {
      const socket = createEventsSocket();
      activeSocket = socket;
      socketRef.current = socket;

      socket.onopen = () => { backoff = 1000; };

      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.type === "node_telemetry") {
            setNodes((current) =>
              current.map((n) =>
                n.id === parsed.node_id
                  ? { ...n, cpu: parsed.cpu, ram: parsed.ram, disk: parsed.disk, temperature: parsed.temperature, uptime: parsed.uptime, status: "online", last_seen: parsed.timestamp }
                  : n
              )
            );
            setLiveTelemetryPoints((prev) => ({
              ...prev,
              [parsed.node_id]: { timestamp: parsed.timestamp, cpu: parsed.cpu, ram: parsed.ram, disk: parsed.disk, temperature: parsed.temperature, battery_pct: parsed.battery_pct, altitude: parsed.altitude },
            }));
            return;
          }
          if (parsed.type === "watch_alert") {
            setWatchAlerts((current) => {
              if (current.some((a) => a.id === parsed.alert.id)) return current;
              return [parsed.alert, ...current];
            });
            return;
          }
          if (parsed.type === "watch_resolve") {
            setWatchAlerts((current) => current.filter((a) => a.rule_key !== parsed.rule_key));
            return;
          }
          if (parsed.type === "node_deleted") {
            setNodes((current) => current.filter((n) => n.id !== parsed.node_id));
            return;
          }
          if (parsed.type === "node_added") {
            setNodes((current) => [...current.filter((n) => n.id !== parsed.node.id), parsed.node]);
            return;
          }
          if (parsed.type === "service_added" || parsed.type === "service_updated" || parsed.type === "service_deleted") {
            window.dispatchEvent(new CustomEvent("silvia:services_changed", { detail: { node_name: parsed.node_name, service_name: parsed.service_name } }));
            return;
          }
          setLogs((current) => [...current.slice(-99), parsed]);
        } catch {
          // ignore malformed frames
        }
      };

      socket.onerror = () => {};
      socket.onclose = () => {
        if (!dead) {
          reconnectTimer = setTimeout(() => {
            backoff = Math.min(backoff * 2, 30000);
            connect();
          }, backoff);
        }
      };
    }

    connect();
    return () => {
      dead = true;
      clearTimeout(reconnectTimer);
      activeSocket?.close();
    };
  }, []);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const nodesData = await fetchNodes();
        setNodes(nodesData);
      } catch {}
    }, 65000);
    return () => clearInterval(interval);
  }, []);

  // ── Auto-TTS ──────────────────────────────────────────────────────────────────
  // Fallback TTS path for completed (non-streaming) voice responses — e.g. decision mode.
  // Streaming voice responses are handled by SentenceStreamTTS in submitQuery, which
  // pre-marks the message ID so this effect never re-speaks them.
  //
  // IMPORTANT: Do NOT add voice?.speech_enabled to the dependency array.
  // speech_enabled toggling between true/false during playback would re-run this effect
  // and find unspoken old messages, causing SILVIA to speak chat history.
  useEffect(() => {
    // STABLE MODE: auto-TTS is fully disabled. Speech only plays via the manual
    // replay button (replayLastResponse). The conversational auto-speak path runs
    // ONLY in presence_experimental mode.
    if (voiceModeRef.current !== "presence_experimental") return;

    const latestAssistant = [...messages].reverse().find(
      (m) => m.role === "assistant" && !m.isStreaming && !ttsSpokenIdsRef.current.has(m.id)
    );
    if (!latestAssistant) return;

    const s = voiceSettingsRef.current;
    const isVoiceResp = latestAssistant._isVoiceResponse;
    // Only speak messages explicitly tagged as voice responses with autoSpeak on.
    // Never trigger from speech_enabled — that flag changes mid-playback and causes
    // all unspoken history to be synthesized.
    const shouldSpeak = isVoiceResp && s.autoSpeak;
    if (!shouldSpeak) return;

    const speechText = latestAssistant.payload?.speech_text || latestAssistant.answer;
    if (!speechText?.trim()) return;

    // Mark spoken via ref (not state) — no re-render, no self-cancellation
    ttsSpokenIdsRef.current.add(latestAssistant.id);

    let cancelled = false;
    const TTS_TIMEOUT_MS = 8000;

    // Split into sentences for parallel synthesis — dramatically reduces perceived latency.
    // All sentences are fetched concurrently; they play sequentially.
    function splitSentences(text) {
      const parts = text.match(/[^.!?]+[.!?]+/g);
      if (!parts || parts.length === 0) return [text];
      return parts.map((p) => p.trim()).filter(Boolean);
    }

    async function speak() {
      // Cancel any previous TTS before starting
      if (ttsBargeCleanupRef.current) { ttsBargeCleanupRef.current(); ttsBargeCleanupRef.current = null; }
      if (ttsSrcRef.current) { try { ttsSrcRef.current.stop(); } catch {} ttsSrcRef.current = null; }
      if (ttsCtxRef.current) { ttsCtxRef.current.close().catch(() => {}); ttsCtxRef.current = null; }

      const sentences = splitSentences(speechText);

      // Kick off ALL sentence TTS requests in parallel — each has its own timeout
      const bufferPromises = sentences.map((sent) =>
        Promise.race([
          synthesizeSpeech(sent),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error(`TTS timeout for: "${sent.slice(0, 30)}..."`)), TTS_TIMEOUT_MS)
          ),
        ])
      );

      // Wait for first sentence to be ready before setting speaking state
      let firstBuffer;
      try {
        firstBuffer = await bufferPromises[0];
      } catch (err) {
        console.error("[TTS] first sentence failed:", err.message);
        return; // can't speak at all — don't change speaking state
      }
      if (cancelled) return;

      // Audio is ready — NOW set speaking (not before, so voice loop isn't frozen during synthesis)
      setVoice((v) => (v ? { ...v, speaking: true } : v));
      updateVoiceState({ speaking: true, speech_enabled: true }).catch(() => {});

      const ctx = new AudioContext();
      ttsCtxRef.current = ctx;

      // Start barge-in VAD on the shared audio context
      if (s.bargeIn) {
        navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }).then((bargeStream) => {
          if (cancelled || !ttsCtxRef.current) { bargeStream.getTracks().forEach((t) => t.stop()); return; }
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 512;
          ctx.createMediaStreamSource(bargeStream).connect(analyser);
          const data = new Float32Array(analyser.fftSize);
          let count = 0;

          function cleanup() {
            if (bargeTimer) { clearInterval(bargeTimer); bargeTimer = null; }
            bargeStream.getTracks().forEach((t) => t.stop());
            ttsBargeCleanupRef.current = null;
          }

          let bargeTimer = setInterval(() => {
            if (!ttsSrcRef.current) { cleanup(); return; }
            analyser.getFloatTimeDomainData(data);
            const rms = Math.sqrt(data.reduce((sum, v) => sum + v * v, 0) / data.length);
            if (rms > 0.018) {
              count++;
              if (count >= 4) { // ~200ms sustained speech — barge-in
                cleanup();
                try { ttsSrcRef.current?.stop(); } catch {}
              }
            } else { count = Math.max(0, count - 1); }
          }, 50);

          ttsBargeCleanupRef.current = cleanup;
        }).catch(() => {});
      }

      // Play each sentence sequentially
      const allBuffers = [firstBuffer, ...await Promise.allSettled(bufferPromises.slice(1))
        .then((results) => results.map((r) => (r.status === "fulfilled" ? r.value : null)))];

      for (let i = 0; i < allBuffers.length; i++) {
        if (cancelled) break;
        const buf = allBuffers[i];
        if (!buf) continue; // sentence timed out — skip it

        let decoded;
        try {
          decoded = await ctx.decodeAudioData(buf);
        } catch {
          continue;
        }
        if (cancelled) break;

        await new Promise((resolve) => {
          const src = ctx.createBufferSource();
          ttsSrcRef.current = src;
          src.buffer = decoded;
          src.connect(ctx.destination);
          src.onended = resolve;
          src.start();
        });

        ttsSrcRef.current = null;
        if (cancelled) break;
      }

      // All sentences done (or cancelled)
      if (ttsBargeCleanupRef.current) { ttsBargeCleanupRef.current(); ttsBargeCleanupRef.current = null; }
      ttsCtxRef.current = null;
      ctx.close().catch(() => {});
      if (!cancelled) {
        setVoice((v) => (v ? { ...v, speaking: false } : v));
        updateVoiceState({ speaking: false, speech_enabled: true }).catch(() => {});
      }
    }

    speak().catch((err) => {
      console.error("[TTS] speak() unhandled:", err);
      setVoice((v) => (v ? { ...v, speaking: false } : v));
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]); // intentionally omit voice?.speech_enabled — see comment above

  // ── Replay last response ──────────────────────────────────────────────────────
  async function replayLastResponse() {
    const latest = [...messages].reverse().find((m) => m.role === "assistant");
    const text = latest?.payload?.speech_text || latest?.answer;
    if (!text?.trim()) return;

    stopSpeaking();

    try {
      setVoice((v) => (v ? { ...v, speaking: true } : v));
      const buffer = await synthesizeSpeech(text);
      const ctx = new AudioContext();
      ttsCtxRef.current = ctx;
      const decoded = await ctx.decodeAudioData(buffer);
      const src = ctx.createBufferSource();
      ttsSrcRef.current = src;
      src.buffer = decoded;
      src.connect(ctx.destination);
      src.onended = () => {
        ttsSrcRef.current = null;
        ttsCtxRef.current = null;
        ctx.close().catch(() => {});
        setVoice((v) => (v ? { ...v, speaking: false } : v));
      };
      src.start();
    } catch {
      setVoice((v) => (v ? { ...v, speaking: false } : v));
    }
  }

  function setVoiceMode(next) {
    if (!VOICE_MODES.includes(next)) return;
    // Leaving the conversational pipeline → kill any in-flight speech.
    if (next !== "presence_experimental") stopSpeaking();
    try { localStorage.setItem("silvia_voice_mode", next); } catch {}
    _setVoiceMode(next);
    console.info(`[VOICE_MODE_CHANGE] -> ${next}`);
  }

  async function switchMode(nextMode) {
    setError("");
    const data = await setMode(nextMode);
    setModeState(data.active_mode);
    setModeReason(data.reason);
  }

  submitQueryRef.current = submitQuery;

  async function submitQuery(value = draft, opts = {}) {
    const trimmed = value.trim();
    if (!trimmed || pending) return { ok: false, expectsReply: false };
    const metadata = opts.voice ? { voice: true } : {};
    const isVoice = !!opts.voice;

    setPending(true);
    setError("");
    setDraft("");

    setMessages((current) => [...current, {
      id: `user-${Date.now()}`,
      role: "user",
      answer: trimmed,
    }]);

    // Declared outside the try so the catch block can safely cancel it.
    let streamTTS = null;
    // Backend-determined: does SILVIA's reply expect the user to respond?
    // (intent-classified server-side — see expects_reply on the response/done event)
    let backendExpectsReply = false;

    try {
      if (mode === "decision") {
        const response = await sendDecision({ query: trimmed, mode: "decision", session_id: sessionId });
        setMessages((current) => [...current, {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          _isVoiceResponse: isVoice,
          ...response,
        }]);
        return { ok: true, expectsReply: !!response?.expects_reply };
      }

      const streamMsgId = `assistant-stream-${Date.now()}`;
      setMessages((current) => [...current, {
        id: streamMsgId,
        role: "assistant",
        mode: "conversation",
        title: "SILVIA",
        answer: "",
        isStreaming: true,
        confidence: 0,
        sources: [],
        agents: [],
        logs: [],
        payload: {},
        _isVoiceResponse: isVoice,
      }]);

      // ── Sentence streaming TTS (presence_fast pipeline) ──────────────────
      // For voice requests: TTS starts on the FIRST complete sentence from the
      // LLM stream — before the response is done. This cuts perceived latency
      // from "full response + synthesis" to "first sentence + synthesis".
      if (isVoice && voiceModeRef.current === "presence_experimental" && voiceSettingsRef.current.autoSpeak) {
        stopSpeaking(); // cancel any previous audio

        // Pre-mark ALL existing assistant messages as spoken.
        // This prevents the auto-TTS useEffect from retroactively speaking
        // old messages when it next fires after messages state updates.
        messagesRef.current.forEach((m) => {
          if (m.role === "assistant") ttsSpokenIdsRef.current.add(m.id);
        });
        // Pre-mark the new stream message too
        ttsSpokenIdsRef.current.add(streamMsgId);

        const turnId = `vt_${Date.now()}`;
        console.info(`[TTS_QUEUE_CLEAR] reason=new_turn turn_id=${turnId}`);

        streamTTS = streamTTSRef.current = new SentenceStreamTTS({
          turnId,
          synthesize: synthesizeSpeech,
          onSpeakingChange: (speaking) => {
            setVoice((v) => (v ? { ...v, speaking } : v));
            updateVoiceState({ speaking, speech_enabled: true }).catch(() => {});
          },
          onLatency: (lat) => {
            console.info("[Voice pipeline] Latency →", lat);
          },
        });
      }

      await sendChatStream(
        { query: trimmed, mode: "conversation", session_id: sessionId, metadata },
        (chunk) => {
          if (chunk.type === "token") {
            setMessages((current) => current.map((msg) =>
              msg.id === streamMsgId
                ? { ...msg, answer: (msg.answer || "") + chunk.token }
                : msg
            ));
            // Feed token into sentence chunker — TTS starts on first complete sentence
            if (streamTTS) streamTTS.feed(chunk.token);

          } else if (chunk.type === "full") {
            backendExpectsReply = !!chunk.response?.expects_reply;
            setMessages((current) => current.map((msg) =>
              msg.id === streamMsgId
                ? { id: streamMsgId, role: "assistant", isStreaming: false, _isVoiceResponse: isVoice, ...chunk.response }
                : msg
            ));
            const nav = chunk.response?.payload?.internal_navigation;
            if (nav?.route) {
              window.open(`${window.location.origin}${nav.route}`, "_blank", "noopener,noreferrer");
            }
            // Instant tool response — speak the full text immediately
            if (streamTTS) {
              const speechText = chunk.response?.payload?.speech_text || chunk.response?.answer || "";
              if (speechText) streamTTS.feedFull(speechText);
            }

          } else if (chunk.type === "done") {
            backendExpectsReply = !!chunk.expects_reply;
            setMessages((current) => current.map((msg) =>
              msg.id === streamMsgId
                ? {
                    ...msg,
                    isStreaming: false,
                    processing_time_ms: chunk.processing_time_ms,
                    agents: chunk.agents ?? [],
                    logs: chunk.logs ?? [],
                    payload: {
                      ...msg.payload,
                      speech_text: chunk.speech_text,
                    },
                    _isVoiceResponse: isVoice,
                  }
                : msg
            ));
            // Flush any remaining buffered tokens to TTS
            if (streamTTS) streamTTS.flush();
          }
        }
      );

      return { ok: true, expectsReply: backendExpectsReply };
    } catch (submitError) {
      if (streamTTS) streamTTS.cancel();
      setError(submitError.message || "Request failed.");
      return { ok: false, expectsReply: false };
    } finally {
      // Don't clear streamTTSRef here — audio may still be playing after the stream closes
      setPending(false);
    }
  }

  async function runAction(action) {
    try {
      return await openAppAction(action.id, []);
    } catch (actionError) {
      setError(actionError.message || "Action failed.");
      throw actionError;
    }
  }

  async function runAliasAction(target) {
    try {
      return await executeActionAlias(target);
    } catch (actionError) {
      setError(actionError.message || "Alias action failed.");
      throw actionError;
    }
  }

  async function applyAudio(action, value) {
    try {
      let next;
      if (action === "up") next = await volumeUp();
      if (action === "down") next = await volumeDown();
      if (action === "mute") next = await toggleMute();
      if (action === "set") next = await setAudioVolume(value);
      if (action === "play_pause") await mediaPlayPause();
      if (action === "next") await mediaNext();
      if (action === "previous") await mediaPrevious();
      if (next) setAudio(next);
    } catch (audioError) {
      setError(audioError.message || "Audio control failed.");
    }
  }

  async function setVoiceFlags(payload) {
    try {
      const next = await updateVoiceState(payload);
      setVoice(next);
      return next;
    } catch (voiceError) {
      setError(voiceError.message || "Voice update failed.");
      throw voiceError;
    }
  }

  async function clearChat() {
    try {
      ttsSpokenIdsRef.current = new Set();
      await clearHistory(sessionId);
      setMessages([{
        id: "cleared",
        role: "assistant",
        mode: "conversation",
        title: "Memory Cleared",
        answer: "Conversation history has been cleared. Starting fresh.",
        processing_time_ms: 0,
        sources: [],
        agents: [],
        logs: [],
        payload: {},
      }]);
    } catch (clearError) {
      setError(clearError.message || "Failed to clear history.");
    }
  }

  function openIntelBoard() {
    window.open(`${window.location.origin}/intel`, "_blank", "noopener,noreferrer");
  }

  function openHardwareBoard() {
    window.open(`${window.location.origin}/hardware`, "_blank", "noopener,noreferrer");
  }

  async function addNode(data) {
    try {
      const node = await createNode(data);
      setNodes((current) => [...current.filter((existing) => existing.id !== node.id), node]);
      return node;
    } catch (nodeError) {
      setError(nodeError.message || "Failed to add node.");
      throw nodeError;
    }
  }

  async function removeNode(nodeId) {
    try {
      await deleteNode(nodeId);
      setNodes((current) => current.filter((n) => n.id !== nodeId));
    } catch (nodeError) {
      setError(nodeError.message || "Failed to remove node.");
      throw nodeError;
    }
  }

  async function saveNode(nodeId, data) {
    try {
      const next = await updateNode(nodeId, data);
      setNodes((current) => current.map((node) => (node.id === nodeId ? next : node)));
      return next;
    } catch (nodeError) {
      setError(nodeError.message || "Failed to update node.");
      throw nodeError;
    }
  }

  async function probeNodeById(nodeId) {
    try {
      const next = await probeNode(nodeId);
      setNodes((current) => current.map((node) => (node.id === nodeId ? next : node)));
      return next;
    } catch (nodeError) {
      setError(nodeError.message || "Failed to probe node.");
      throw nodeError;
    }
  }

  async function verifyNodeById(nodeId) {
    try {
      const next = await verifyNode(nodeId);
      setNodes((current) => current.map((node) => (node.id === nodeId ? next : node)));
      return next;
    } catch (verifyError) {
      setError(verifyError.message || "Failed to verify node.");
      throw verifyError;
    }
  }

  async function dismissAlert(alertId) {
    try {
      await dismissWatchAlert(alertId);
      setWatchAlerts((current) => current.filter((a) => a.id !== alertId));
    } catch (alertError) {
      setError(alertError.message || "Failed to dismiss alert.");
    }
  }

  return {
    mode,
    modeReason,
    voice,
    audio,
    devices,
    nodes,
    watchAlerts,
    liveTelemetryPoints,
    actions,
    draft,
    messages,
    logs,
    pending,
    error,
    sessionId,
    setError,
    setDraft,
    switchMode,
    submitQuery,
    runAction,
    runAliasAction,
    applyAudio,
    setVoiceFlags,
    clearChat,
    openIntelBoard,
    openHardwareBoard,
    addNode,
    saveNode,
    probeNodeById,
    verifyNodeById,
    removeNode,
    dismissAlert,
    voiceLoopEnabled,
    setVoiceLoopEnabled: (updater) => {
      setVoiceLoopEnabled((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater;
        try { localStorage.setItem("silvia_voice_loop_enabled", String(next)); } catch {}
        return next;
      });
    },
    voiceLoopState,
    voiceLoopError,
    voiceMode,
    voiceModeOptions: VOICE_MODES,
    setVoiceMode,
    voiceSettings,
    updateVoiceSetting,
    stopSpeaking,
    replayLastResponse,
  };
}
