import { useEffect, useRef, useState } from "react";

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

export function useCommandCenterData() {
  const [mode, setModeState] = useState("conversation");
  const [modeReason, setModeReason] = useState("Loading");
  const [voice, setVoice] = useState(null);
  const [audio, setAudio] = useState(null);
  const [devices, setDevices] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [watchAlerts, setWatchAlerts] = useState([]);
  const [actions, setActions] = useState([]);
  const [draft, setDraft] = useState("");
  const [sessionId] = useState("default-session");
  const [messages, setMessages] = useState([]);
  const [logs, setLogs] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const socketRef = useRef(null);

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

        // Restore conversation history, then add welcome if empty
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

      socket.onopen = () => {
        backoff = 1000;
      };

      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.type === "node_telemetry") {
            setNodes((current) =>
              current.map((n) =>
                n.id === parsed.node_id
                  ? {
                      ...n,
                      cpu: parsed.cpu,
                      ram: parsed.ram,
                      disk: parsed.disk,
                      temperature: parsed.temperature,
                      uptime: parsed.uptime,
                      status: "online",
                      last_seen: parsed.timestamp,
                    }
                  : n
              )
            );
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
            setWatchAlerts((current) =>
              current.filter((a) => a.rule_key !== parsed.rule_key)
            );
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

  useEffect(() => {
    if (!voice?.speech_enabled) {
      return;
    }
    // Skip messages still streaming or where TTS was already handled inline
    const latestAssistant = [...messages].reverse().find(
      (message) => message.role === "assistant" && !message.isStreaming && !message.payload?._ttsHandled
    );
    const speechText = latestAssistant?.payload?.speech_text || latestAssistant?.answer;
    if (!speechText) {
      return;
    }

    let cancelled = false;

    async function speak() {
      let ctx;
      try {
        setVoice((current) => (current ? { ...current, speaking: true } : current));
        await updateVoiceState({ speaking: true, speech_enabled: true });
        const buffer = await synthesizeSpeech(speechText);
        if (cancelled) return;
        ctx = new AudioContext();
        const decoded = await ctx.decodeAudioData(buffer);
        const src = ctx.createBufferSource();
        src.buffer = decoded;
        src.connect(ctx.destination);
        src.onended = async () => {
          await ctx.close();
          if (!cancelled) {
            setVoice((current) => (current ? { ...current, speaking: false } : current));
            await updateVoiceState({ speaking: false, speech_enabled: true });
          }
        };
        src.start();
      } catch (playbackError) {
        if (ctx) await ctx.close().catch(() => {});
        if (!cancelled) {
          setError(playbackError.message || "Voice playback failed.");
          setVoice((current) => (current ? { ...current, speaking: false } : current));
          await updateVoiceState({ speaking: false, speech_enabled: true });
        }
      }
    }

    speak();

    return () => {
      cancelled = true;
    };
  }, [messages, voice?.speech_enabled]);

  async function switchMode(nextMode) {
    setError("");
    const data = await setMode(nextMode);
    setModeState(data.active_mode);
    setModeReason(data.reason);
  }

  async function submitQuery(value = draft) {
    const trimmed = value.trim();
    if (!trimmed || pending) return false;

    setPending(true);
    setError("");
    setDraft("");

    setMessages((current) => [...current, {
      id: `user-${Date.now()}`,
      role: "user",
      answer: trimmed,
    }]);

    try {
      if (mode === "decision") {
        const response = await sendDecision({ query: trimmed, mode: "decision", session_id: sessionId });
        setMessages((current) => [...current, {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          ...response,
        }]);
        return true;
      }

      // Streaming conversation path
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
      }]);

      // Capture current speech state for use inside stream callback
      const speechEnabled = voice?.speech_enabled ?? false;
      let firstSentenceSpoken = false;
      let ttsText = "";
      const SENTENCE_RE = /^.+?[.!?](?:\s|$)/s;

      await sendChatStream(
        { query: trimmed, mode: "conversation", session_id: sessionId },
        (chunk) => {
          if (chunk.type === "token") {
            ttsText += chunk.token;
            setMessages((current) => current.map((msg) =>
              msg.id === streamMsgId ? { ...msg, answer: ttsText } : msg
            ));

            // Sentence-level TTS: speak first complete sentence immediately
            if (!firstSentenceSpoken && speechEnabled) {
              const m = SENTENCE_RE.exec(ttsText);
              if (m) {
                firstSentenceSpoken = true;
                const firstSentence = m[0].trim();
                synthesizeSpeech(firstSentence).then(async (buffer) => {
                  try {
                    const ctx = new AudioContext();
                    const decoded = await ctx.decodeAudioData(buffer);
                    const src = ctx.createBufferSource();
                    src.buffer = decoded;
                    src.connect(ctx.destination);
                    setVoice((v) => v ? { ...v, speaking: true } : v);
                    updateVoiceState({ speaking: true, speech_enabled: true }).catch(() => {});
                    src.onended = () => {
                      ctx.close();
                      setVoice((v) => v ? { ...v, speaking: false } : v);
                      updateVoiceState({ speaking: false, speech_enabled: true }).catch(() => {});
                    };
                    src.start();
                  } catch (_) {}
                }).catch(() => {});
              }
            }

          } else if (chunk.type === "full") {
            // Instant tool/action/memory result — replace streaming placeholder
            setMessages((current) => current.map((msg) =>
              msg.id === streamMsgId
                ? { id: streamMsgId, role: "assistant", isStreaming: false, ...chunk.response }
                : msg
            ));

          } else if (chunk.type === "done") {
            // LLM stream finished — finalize message; mark TTS handled if sentence 1 was spoken
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
                      _ttsHandled: firstSentenceSpoken,
                    },
                  }
                : msg
            ));
          }
        }
      );

      return true;
    } catch (submitError) {
      setError(submitError.message || "Request failed.");
      return false;
    } finally {
      setPending(false);
    }
  }

  async function runAction(action) {
    try {
      const result = await openAppAction(action.id, []);
      return result;
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
    addNode,
    saveNode,
    probeNodeById,
    verifyNodeById,
    removeNode,
    dismissAlert,
  };
}
