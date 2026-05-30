import { useEffect, useRef, useState } from "react";

import {
  clearHistory,
  createEventsSocket,
  executeActionAlias,
  fetchActions,
  fetchAudioState,
  fetchDevices,
  fetchHistory,
  fetchLogs,
  fetchMode,
  fetchRoute,
  fetchVoiceStatus,
  mediaNext,
  mediaPlayPause,
  mediaPrevious,
  openAppAction,
  sendChat,
  sendDecision,
  setAudioVolume,
  setMode,
  toggleMute,
  updateVoiceState,
  volumeDown,
  volumeUp,
} from "../lib/api";

const INITIAL_ROUTE = {
  origin: "London",
  destination: "Cambridge",
  travel_mode: "drive",
  distance: "",
  eta: "",
  provider: "",
  notes: [],
  origin_lat: null,
  origin_lon: null,
  destination_lat: null,
  destination_lon: null,
};

export function useCommandCenterData() {
  const [mode, setModeState] = useState("conversation");
  const [modeReason, setModeReason] = useState("Loading");
  const [voice, setVoice] = useState(null);
  const [audio, setAudio] = useState(null);
  const [devices, setDevices] = useState([]);
  const [actions, setActions] = useState([]);
  const [route, setRouteState] = useState(INITIAL_ROUTE);
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
        const [modeData, voiceData, deviceData, actionData, routeData, logData, audioData, historyData] =
          await Promise.all([
            fetchMode(),
            fetchVoiceStatus(),
            fetchDevices(),
            fetchActions(),
            fetchRoute({ origin: INITIAL_ROUTE.origin, destination: INITIAL_ROUTE.destination, travel_mode: "drive" }),
            fetchLogs(),
            fetchAudioState(),
            fetchHistory(sessionId, 100),
          ]);

        setModeState(modeData.active_mode);
        setModeReason(modeData.reason);
        setVoice(voiceData);
        setDevices(deviceData);
        setActions(actionData);
        setRouteState(routeData);
        setLogs(logData);
        setAudio(audioData);

        // Restore conversation history, then add welcome if empty
        if (historyData.messages && historyData.messages.length > 0) {
          const restored = historyData.messages.map((msg, i) => ({
            id: `history-${i}`,
            role: msg.role,
            mode: msg.mode || "conversation",
            answer: msg.content,
            title: msg.role === "assistant" ? "CMD-CTR" : undefined,
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
            title: "Command Center Online",
            answer: "CMD-CTR is live. Conversation history is persisted across sessions. Ask me anything, or say 'open [app]' to launch something.",
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
    const socket = createEventsSocket();
    socketRef.current = socket;
    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setLogs((current) => [...current.slice(-99), parsed]);
      } catch {
        // Ignore malformed messages.
      }
    };
    socket.onerror = () => {
      setError((current) => current || "Live event stream disconnected.");
    };
    return () => {
      socket.close();
    };
  }, []);

  useEffect(() => {
    if (!voice?.speech_enabled) {
      window.speechSynthesis?.cancel();
      return;
    }
    const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");
    if (!latestAssistant?.answer || !window.speechSynthesis) {
      return;
    }

    const utterance = new SpeechSynthesisUtterance(latestAssistant.answer);
    utterance.onstart = async () => {
      try {
        setVoice((current) => (current ? { ...current, speaking: true } : current));
        await updateVoiceState({ speaking: true, speech_enabled: true });
      } catch {
        // no-op
      }
    };
    utterance.onend = async () => {
      try {
        setVoice((current) => (current ? { ...current, speaking: false } : current));
        await updateVoiceState({ speaking: false, speech_enabled: true });
      } catch {
        // no-op
      }
    };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  }, [messages, voice?.speech_enabled]);

  async function switchMode(nextMode) {
    setError("");
    const data = await setMode(nextMode);
    setModeState(data.active_mode);
    setModeReason(data.reason);
  }

  async function submitQuery(value = draft) {
    const trimmed = value.trim();
    if (!trimmed || pending) {
      return false;
    }

    setPending(true);
    setError("");

    const userMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      answer: trimmed,
    };
    setMessages((current) => [...current, userMessage]);

    try {
      const response =
        mode === "decision"
          ? await sendDecision({ query: trimmed, mode: "decision", session_id: sessionId })
          : await sendChat({ query: trimmed, mode: "conversation", session_id: sessionId, metadata: route.origin ? { origin: route.origin } : {} });
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          ...response,
        },
      ]);
      setDraft("");
      return true;
    } catch (submitError) {
      setError(submitError.message || "Request failed.");
      return false;
    } finally {
      setPending(false);
    }
  }

  async function requestRoute({ origin, destination, travel_mode }) {
    try {
      const nextRoute = await fetchRoute({ origin, destination, travel_mode });
      setRouteState(nextRoute);
      return nextRoute;
    } catch (routeError) {
      setError(routeError.message || "Failed to load route.");
      throw routeError;
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

  return {
    mode,
    modeReason,
    voice,
    audio,
    devices,
    actions,
    route,
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
    requestRoute,
    runAction,
    runAliasAction,
    applyAudio,
    setVoiceFlags,
    clearChat,
    openIntelBoard,
  };
}
