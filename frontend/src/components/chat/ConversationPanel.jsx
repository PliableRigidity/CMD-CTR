import { useEffect, useRef, useState } from "react";
import { animate } from "animejs";
import { transcribeAudio, getWakeWsUrl } from "../../lib/api";
import WaveformVisualizer from "../voice/WaveformVisualizer";
import VoiceOrb from "../voice/VoiceOrb";
import RichOutput from "./RichOutput";

function MessageBubble({ message, index }) {
  const seq = `#${String(index + 1).padStart(3, "0")}`;

  if (message.role === "user") {
    return (
      <article className="message message--user">
        <div className="message__header">
          <span className="message__sender">OPERATOR</span>
          <span className="message__rule" aria-hidden="true" />
          <span className="message__tag">{seq}</span>
          <span className="message__tag">TX</span>
        </div>
        <p className="message__body">{message.answer}</p>
      </article>
    );
  }

  return (
    <article className={`message message--assistant${message.isHistory ? " message--history" : ""}`}>
      <div className="message__header">
        <span className="message__sender">{message.title || "SILVIA"}</span>
        <span className="message__rule" aria-hidden="true" />
        <span className="message__tag">{seq}</span>
        <span className="message__tag">{message.mode === "decision" ? "COUNCIL" : "CORE"}</span>
      </div>
      <p className="message__body" style={{ whiteSpace: "pre-wrap" }}>
        {message.answer}
        {message.isStreaming && <span className="stream-cursor">█</span>}
      </p>
      {message.reasoning ? (
        <p className="message__reasoning muted">// {message.reasoning}</p>
      ) : null}
      {message.sources?.length ? (
        <div className="source-list">
          {message.sources.map((source) => (
            <a key={source.url} className="source-card" href={source.url} rel="noreferrer" target="_blank">
              <strong>{source.title}</strong>
              <span>{source.source}</span>
              {source.snippet ? <p>{source.snippet}</p> : null}
            </a>
          ))}
        </div>
      ) : null}
      {message.payload?.rich_output && <RichOutput payload={message.payload} />}
    </article>
  );
}

function VoiceDiagPanel({ diag, onClose }) {
  if (!diag) return (
    <div className="voice-diag">
      <div className="voice-diag__header">
        <span>STT Diagnostics</span>
        <button className="voice-diag__close" onClick={onClose}>×</button>
      </div>
      <p style={{ color: "var(--muted)", fontSize: "0.75rem", padding: "8px 0" }}>
        No diagnostics yet — use the mic first.
      </p>
    </div>
  );

  const conf = diag.transcription_confidence != null ? `${(diag.transcription_confidence * 100).toFixed(0)}%` : "—";
  const dur = diag.duration_seconds != null ? `${diag.duration_seconds.toFixed(2)}s` : "—";
  const size = diag.audio_size_bytes != null ? `${(diag.audio_size_bytes / 1024).toFixed(1)} kB` : "—";
  const noSpeechProb = diag.no_speech_probability != null ? `${(diag.no_speech_probability * 100).toFixed(0)}%` : "—";
  const speechColor = diag.speech_detected ? "var(--accent-warm)" : "var(--danger)";

  return (
    <div className="voice-diag">
      <div className="voice-diag__header">
        <span>STT Diagnostics</span>
        <button className="voice-diag__close" onClick={onClose}>×</button>
      </div>
      <div className="voice-diag__grid">
        <span>Provider</span><span>{diag.provider || "local-whisper"}</span>
        <span>Duration</span><span>{dur}</span>
        <span>Size</span><span>{size}</span>
        <span>Format</span><span>{diag.detected_extension || diag.mime_type || "—"}</span>
        <span>Speech detected</span>
        <span style={{ color: speechColor }}>{diag.speech_detected ? "yes" : "no"}</span>
        {diag.vad_max_ema != null && (<><span>Silero VAD EMA</span><span>{(diag.vad_max_ema * 100).toFixed(1)}%</span></>)}
        {diag.vad_speech_ratio != null && (<><span>VAD speech ratio</span><span>{(diag.vad_speech_ratio * 100).toFixed(0)}% of frames</span></>)}
        <span>Confidence</span><span>{conf}</span>
        <span>No-speech prob</span><span>{noSpeechProb}</span>
        <span>Fallback used</span>
        <span style={{ color: diag.fallback_used ? "var(--danger)" : "var(--accent-warm)" }}>
          {diag.fallback_used ? "yes (filtered)" : "no"}
        </span>
        {diag.language && (
          <><span>Language</span><span>{diag.language}{diag.language_probability != null ? ` (${(diag.language_probability * 100).toFixed(0)}%)` : ""}</span></>
        )}
        {diag.raw_transcript != null && (
          <><span>Raw transcript</span><span className="voice-diag__transcript">{diag.raw_transcript ? `"${diag.raw_transcript}"` : "(empty)"}</span></>
        )}
        {diag.final_transcript != null && (
          <><span>Final transcript</span><span className="voice-diag__transcript">{diag.final_transcript ? `"${diag.final_transcript}"` : "(filtered)"}</span></>
        )}
      </div>
    </div>
  );
}

function VoiceSettingsPanel({ settings, onUpdate, onClose }) {
  const timeout = settings?.conversationTimeoutMs ?? 8000;
  return (
    <div className="voice-settings-popover">
      <div className="voice-settings-head">
        <span>VOICE SETTINGS</span>
        <button className="voice-diag__close" onClick={onClose}>×</button>
      </div>
      <div className="voice-settings-body">
        <label className="voice-setting-row">
          <span>Auto-Speak</span>
          <span className="voice-setting-hint">Speak responses to voice commands</span>
          <button
            className={`voice-toggle${settings?.autoSpeak ? " voice-toggle--on" : ""}`}
            onClick={() => onUpdate("autoSpeak", !settings?.autoSpeak)}
          >
            {settings?.autoSpeak ? "ON" : "OFF"}
          </button>
        </label>
        <label className="voice-setting-row">
          <span>Barge-In</span>
          <span className="voice-setting-hint">Interrupt SILVIA while speaking</span>
          <button
            className={`voice-toggle${settings?.bargeIn ? " voice-toggle--on" : ""}`}
            onClick={() => onUpdate("bargeIn", !settings?.bargeIn)}
          >
            {settings?.bargeIn ? "ON" : "OFF"}
          </button>
        </label>
        <label className="voice-setting-row">
          <span>Continuous Conversation</span>
          <span className="voice-setting-hint">Keep mic open between turns</span>
          <button
            className={`voice-toggle${settings?.continuousConversation ? " voice-toggle--on" : ""}`}
            onClick={() => onUpdate("continuousConversation", !settings?.continuousConversation)}
          >
            {settings?.continuousConversation ? "ON" : "OFF"}
          </button>
        </label>
        <label className="voice-setting-row">
          <span>Conversation Timeout</span>
          <span className="voice-setting-hint">Silence before returning to sleep</span>
          <select
            className="voice-select"
            value={timeout}
            onChange={(e) => onUpdate("conversationTimeoutMs", parseInt(e.target.value))}
          >
            <option value={5000}>5 s</option>
            <option value={8000}>8 s</option>
            <option value={12000}>12 s</option>
            <option value={30000}>30 s</option>
          </select>
        </label>
      </div>
    </div>
  );
}

export default function ConversationPanel({
  messages,
  pending,
  error,
  mode,
  draft,
  voice,
  onDraftChange,
  onSubmit,
  onClear,
  onVoiceStateChange,
  onError,
  onStopSpeaking,
  onReplayLast,
  voiceLoopEnabled = false,
  onVoiceLoopToggle,
  voiceLoopState = "idle",
  voiceLoopError = null,
  voiceSettings,
  onUpdateVoiceSetting,
}) {
  const listRef = useRef(null);
  const inputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const [stream, setStream] = useState(null);
  const [recordingState, setRecordingState] = useState("idle");
  const [conversationMode, setConversationMode] = useState(false);
  const [wakeWordMode, setWakeWordMode] = useState(false);
  const [lastDiag, setLastDiag] = useState(null);
  const [showDiag, setShowDiag] = useState(false);
  const [showVoiceSettings, setShowVoiceSettings] = useState(false);

  const inputBayRef = useRef(null);
  const prevMessageCountRef = useRef(0);

  const conversationModeRef = useRef(false);
  const recordingStateRef = useRef("idle");
  const pendingRef = useRef(false);
  const speakingRef = useRef(false);
  const shouldAutoListenRef = useRef(false);
  const wakeWordModeRef = useRef(false);
  const wakeWsRef = useRef(null);
  const wakeAudioCtxRef = useRef(null);
  const wakeProcessorRef = useRef(null);
  const wakeStreamRef = useRef(null);

  useEffect(() => { conversationModeRef.current = conversationMode; }, [conversationMode]);
  useEffect(() => { recordingStateRef.current = recordingState; }, [recordingState]);
  useEffect(() => { pendingRef.current = pending; }, [pending]);
  useEffect(() => { speakingRef.current = !!voice?.speaking; }, [voice?.speaking]);
  useEffect(() => { wakeWordModeRef.current = wakeWordMode; }, [wakeWordMode]);
  useEffect(() => { startListeningRef.current = startListening; });

  useEffect(() => () => _stopWakeWord(), []);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, pending]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const count = messages.length;
    if (count > prevMessageCountRef.current && listRef.current) {
      const items = listRef.current.querySelectorAll(".message");
      const last = items[items.length - 1];
      if (last) {
        animate(last, { opacity: [0, 1], translateY: [7, 0], duration: 210, ease: "outCubic" });
      }
    }
    prevMessageCountRef.current = count;
  }, [messages.length]);

  useEffect(() => {
    if (pending && inputBayRef.current) {
      animate(inputBayRef.current, {
        borderColor: ["rgba(0,229,255,0.70)", "rgba(0,229,255,0.42)"],
        duration: 500,
        ease: "outQuad",
      });
    }
  }, [pending]);

  // Conversation mode: auto-listen after SILVIA finishes responding and speaking
  const prevPendingRef = useRef(false);
  const startListeningRef = useRef(null);

  useEffect(() => {
    const pendingJustEnded = prevPendingRef.current && !pending;
    prevPendingRef.current = pending;

    if (pendingJustEnded && conversationMode) {
      shouldAutoListenRef.current = true;
    }

    if (
      shouldAutoListenRef.current &&
      !pending &&
      !voice?.speaking &&
      recordingState === "idle"
    ) {
      shouldAutoListenRef.current = false;
      const t = setTimeout(() => {
        if (conversationModeRef.current && recordingStateRef.current === "idle" && !pendingRef.current && !speakingRef.current) {
          startListeningRef.current?.();
        }
      }, 700);
      return () => clearTimeout(t);
    }
  }, [pending, voice?.speaking, conversationMode, recordingState]);

  const silenceTimerRef = useRef(null);
  const hasSpokenRef = useRef(false);
  const vadIntervalRef = useRef(null);
  const vadAudioCtxRef = useRef(null);

  function _clearVad() {
    if (vadIntervalRef.current) { clearInterval(vadIntervalRef.current); vadIntervalRef.current = null; }
    if (silenceTimerRef.current) { clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null; }
    if (vadAudioCtxRef.current) { vadAudioCtxRef.current.close().catch(() => {}); vadAudioCtxRef.current = null; }
    hasSpokenRef.current = false;
  }

  function _stopWakeWord() {
    if (wakeWsRef.current) { wakeWsRef.current.close(); wakeWsRef.current = null; }
    if (wakeProcessorRef.current) { wakeProcessorRef.current.disconnect(); wakeProcessorRef.current = null; }
    if (wakeAudioCtxRef.current) { wakeAudioCtxRef.current.close().catch(() => {}); wakeAudioCtxRef.current = null; }
    if (wakeStreamRef.current) { wakeStreamRef.current.getTracks().forEach((t) => t.stop()); wakeStreamRef.current = null; }
  }

  async function toggleWakeWordMode() {
    if (wakeWordMode) {
      _stopWakeWord();
      setWakeWordMode(false);
      return;
    }
    try {
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      wakeStreamRef.current = micStream;

      const ctx = new AudioContext({ sampleRate: 16000 });
      wakeAudioCtxRef.current = ctx;

      const ws = new WebSocket(getWakeWsUrl());
      wakeWsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.wake && msg.accepted && recordingStateRef.current === "idle" && !pendingRef.current && !speakingRef.current) {
            startListeningRef.current?.();
          }
        } catch {}
      };

      ws.onclose = (ev) => {
        if (wakeWordModeRef.current) {
          setWakeWordMode(false);
          onError?.(`Wake word disconnected (code ${ev.code})`);
        }
      };

      await new Promise((resolve, reject) => {
        ws.onopen = resolve;
        const t = setTimeout(() => reject(new Error("WebSocket timed out")), 15000);
        ws.onerror = () => { clearTimeout(t); reject(new Error("WebSocket error")); };
      });

      ws.onclose = (ev) => {
        if (wakeWordModeRef.current) {
          setWakeWordMode(false);
          onError?.(`Wake word disconnected (code ${ev.code})`);
        }
      };
      ws.onerror = () => ws.close();

      const source = ctx.createMediaStreamSource(micStream);
      const processor = ctx.createScriptProcessor(1024, 1, 1);
      wakeProcessorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (!wakeWsRef.current || wakeWsRef.current.readyState !== WebSocket.OPEN) return;
        if (recordingStateRef.current !== "idle") return;
        const float32 = e.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)));
        }
        wakeWsRef.current.send(int16.buffer);
      };

      source.connect(processor);
      processor.connect(ctx.destination);
      setWakeWordMode(true);
    } catch (err) {
      _stopWakeWord();
      onError?.(`Wake word failed: ${err.message}`);
    }
  }

  async function startListening() {
    startListeningRef.current = startListening;
    if (recordingStateRef.current !== "idle") return;
    if (pendingRef.current) return;
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      setStream(mic);
      setRecordingState("recording");
      recordingStateRef.current = "recording";
      await onVoiceStateChange?.({ listening: true });

      const preferredTypes = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
      const mimeType = preferredTypes.find((t) => MediaRecorder.isTypeSupported(t)) || "";
      const recorder = mimeType ? new MediaRecorder(mic, { mimeType }) : new MediaRecorder(mic);

      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };

      const SILENCE_THRESHOLD = 15;
      const SILENCE_MS = 600;
      const MIN_SPEECH_MS = 300;
      const MAX_RECORDING_MS = 20000;
      let speechStart = null;

      const maxRecordingTimer = setTimeout(() => {
        if (recordingStateRef.current === "recording") recorder.stop();
      }, MAX_RECORDING_MS);

      try {
        const audioCtx = new AudioContext();
        vadAudioCtxRef.current = audioCtx;
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        const source = audioCtx.createMediaStreamSource(mic);
        source.connect(analyser);
        const freqData = new Uint8Array(analyser.frequencyBinCount);

        hasSpokenRef.current = false;
        vadIntervalRef.current = setInterval(() => {
          analyser.getByteFrequencyData(freqData);
          const avg = freqData.reduce((a, b) => a + b, 0) / freqData.length;

          if (avg > SILENCE_THRESHOLD) {
            if (!hasSpokenRef.current) { hasSpokenRef.current = true; speechStart = Date.now(); }
            if (silenceTimerRef.current) { clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null; }
          } else if (hasSpokenRef.current) {
            const spokenMs = speechStart ? Date.now() - speechStart : 0;
            if (spokenMs >= MIN_SPEECH_MS && !silenceTimerRef.current) {
              silenceTimerRef.current = setTimeout(() => {
                if (recordingStateRef.current === "recording") recorder.stop();
              }, SILENCE_MS);
            }
          }
        }, 100);
      } catch {}

      recorder.onstop = async () => {
        clearTimeout(maxRecordingTimer);
        _clearVad();
        mic.getTracks().forEach((t) => t.stop());
        setStream(null);
        setRecordingState("processing");
        recordingStateRef.current = "processing";
        await onVoiceStateChange?.({ listening: false });

        const actualMime = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: actualMime });

        try {
          const result = await transcribeAudio(blob, actualMime);
          setLastDiag(result.diagnostics || null);
          setRecordingState("idle");
          recordingStateRef.current = "idle";

          if (result.text) {
            await onSubmit(result.text, { voice: true });
          } else if (conversationModeRef.current) {
            setTimeout(() => {
              if (conversationModeRef.current && recordingStateRef.current === "idle" && !pendingRef.current) {
                startListeningRef.current?.();
              }
            }, 1200);
          }
        } catch (err) {
          setRecordingState("idle");
          recordingStateRef.current = "idle";
          onError?.(`Transcription failed: ${err.message}`);
        }
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
    } catch (err) {
      _clearVad();
      setRecordingState("idle");
      recordingStateRef.current = "idle";
      await onVoiceStateChange?.({ listening: false });
      onError?.(`Mic access denied: ${err.message}`);
    }
  }

  function stopListening() {
    _clearVad();
    mediaRecorderRef.current?.stop();
  }

  function toggleConversationMode() {
    const next = !conversationMode;
    setConversationMode(next);
    conversationModeRef.current = next;
    if (next) {
      shouldAutoListenRef.current = false;
      if (recordingStateRef.current === "idle" && !pendingRef.current) {
        setTimeout(() => startListeningRef.current?.(), 300);
      }
    } else {
      shouldAutoListenRef.current = false;
      if (recordingStateRef.current === "recording") stopListening();
    }
  }

  function _flashExec() {
    if (!inputBayRef.current) return;
    animate(inputBayRef.current, {
      borderColor: ["rgba(0,229,255,0.70)", "rgba(0,229,255,0.42)"],
      duration: 420,
      ease: "outQuad",
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    _flashExec();
    await onSubmit(draft);
  }

  async function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      _flashExec();
      await onSubmit(draft);
    }
  }

  const isRecording = recordingState === "recording";
  const isProcessing = recordingState === "processing";
  const isSpeaking = voice?.speaking;

  // Determine VoiceOrb state — priority order: speaking > recording > processing > voice loop > wake word > conversation > idle
  function getOrbState() {
    if (isSpeaking) return "speaking";
    if (pending) return "thinking";
    if (isRecording) return "recording";
    if (isProcessing) return "processing";
    if (voiceLoopEnabled) return voiceLoopState;
    if (wakeWordMode) return "listening";
    if (conversationMode) return "listening";
    return "idle";
  }

  return (
    <section className="panel conversation-panel">
      <div className="panel-heading">
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <VoiceOrb
            state={getOrbState()}
            size={28}
            showLabel={false}
            onClick={isSpeaking ? onStopSpeaking : undefined}
          />
          <div>
            <p className="eyebrow">Mission Core / Assistant Bus</p>
            <h2>Assistant Channel</h2>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {isSpeaking && (
            <button type="button" onClick={onStopSpeaking} className="btn-ghost-sm" style={{ color: "var(--danger)" }}>
              ■ STOP
            </button>
          )}
          {onClear && (
            <button type="button" onClick={onClear} className="btn-ghost-sm">CLEAR</button>
          )}
          <span className={`state-pill state-pill--${pending ? "busy" : "idle"}`}>
            {pending ? "Processing" : mode === "decision" ? "Council Ready" : "Ready"}
          </span>
        </div>
      </div>

      <div className="channel-statusbar">
        <span>{mode === "decision" ? "COUNCIL PATH" : "DIRECT ASSIST PATH"}</span>
        <span>{pending ? "PROCESSING" : "STANDBY"}</span>
        {isRecording && !voiceLoopEnabled && <span style={{ color: "var(--danger)" }}>● LISTENING</span>}
        {isProcessing && !voiceLoopEnabled && <span style={{ color: "var(--accent)" }}>◌ TRANSCRIBING</span>}
        {isSpeaking && <span style={{ color: "#00ff88" }}>● SPEAKING{voiceSettings?.bargeIn ? " · speak to interrupt" : ""}</span>}
        {wakeWordMode && !isRecording && !isSpeaking && (
          <span style={{ color: "var(--accent-warm)", animation: "pulse 2s infinite" }}>◎ WAKE WORD</span>
        )}
        {conversationMode && !wakeWordMode && !isRecording && !isSpeaking && !pending && !voiceLoopEnabled && (
          <span style={{ color: "var(--muted)" }}>⟳ CONVERSATION</span>
        )}
        {voiceLoopEnabled && (
          <span style={{ color: voiceLoopState === "recording" ? "var(--danger)" : voiceLoopState === "speaking" ? "#00ff88" : voiceLoopState === "conversation_active" ? "var(--accent-warm)" : "var(--accent-warm)", animation: "pulse 2s infinite" }}>
            ⊛ {voiceLoopState === "listening" ? "WAKE WORD" : voiceLoopState === "recording" ? "LISTENING" : voiceLoopState === "processing" ? "THINKING" : voiceLoopState === "speaking" ? "SPEAKING" : voiceLoopState === "conversation_active" ? "WAITING FOR REPLY" : voiceLoopState === "listening_again" ? "LISTENING" : voiceLoopState === "cooldown" ? "…" : voiceLoopState.toUpperCase()}
          </span>
        )}
      </div>

      <div className="message-list" ref={listRef}>
        {messages.length === 0 && !pending ? (
          <div className="terminal-boot">
            <p className="boot-line boot-line--ok">SILVIA CORE · ONLINE</p>
            <p className="boot-line boot-line--ok">ASSISTANT BUS · CONNECTED</p>
            <p className="boot-line boot-line--sys">DIRECT CHANNEL OPEN · AWAITING OPERATOR INPUT</p>
            <p className="boot-line boot-line--cursor">_</p>
          </div>
        ) : null}
        {messages.map((msg, i) => <MessageBubble key={msg.id} message={msg} index={i} />)}
        {pending && !messages.some((m) => m.isStreaming) ? (
          <article className="message message--assistant">
            <div className="message__header">
              <span className="message__sender">SILVIA</span>
              <span className="message__rule" aria-hidden="true" />
              <span className="message__tag">CORE</span>
              <span className="message__tag message__tag--busy">PROCESSING</span>
            </div>
            <p className="message__body message__body--processing">
              <span className="stream-cursor">█</span>
            </p>
          </article>
        ) : null}
      </div>

      {error ? <div className="error-banner">{error}</div> : null}
      {voiceLoopError ? <div className="error-banner">Voice: {voiceLoopError}</div> : null}

      {showDiag && <VoiceDiagPanel diag={lastDiag} onClose={() => setShowDiag(false)} />}
      {showVoiceSettings && (
        <VoiceSettingsPanel
          settings={voiceSettings}
          onUpdate={onUpdateVoiceSetting}
          onClose={() => setShowVoiceSettings(false)}
        />
      )}

      <form className="composer" onSubmit={handleSubmit}>
        <div className="composer__inputbay" ref={inputBayRef}>
          <div className="composer__eyebrow">
            <span>Command Input Bay</span>
            <span>Mic auto-sends · Enter to transmit · Shift+Enter for new line</span>
          </div>
          {isRecording && (
            <WaveformVisualizer stream={stream} active={isRecording} />
          )}
          <div className="composer__prompt-row">
            <span className="composer__prompt-prefix" aria-hidden="true">{
              voiceLoopEnabled ? "⊛" : wakeWordMode ? "⊡" : conversationMode ? "⟳" : "//"
            }</span>
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => onDraftChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                voiceLoopEnabled
                  ? "voice mode active · say 'hey silvia' to begin · or type"
                  : wakeWordMode
                  ? "say 'hey silvia' to activate · or type"
                  : conversationMode
                  ? "conversation active · speak or type"
                  : mode === "decision"
                  ? "submit problem for council review"
                  : "issue command, query, or 'open [app]'"
              }
              rows={3}
            />
          </div>
          <div className="composer__footer">
            <div className="voice-controls-inline">

              {/* Primary: Hands-free voice loop */}
              <button
                type="button"
                className={`voice-btn${voiceLoopEnabled ? " voice-btn--conv" : ""}`}
                onClick={onVoiceLoopToggle}
                title={voiceLoopEnabled
                  ? "Voice mode ON — wake word activates mic, SILVIA speaks back automatically"
                  : "Voice mode — hands-free conversation with SILVIA"}
              >
                {voiceLoopEnabled ? "⊛ Voice ON" : "⊛ Voice"}
              </button>

              {/* Wake word (standalone, without full loop) */}
              {!voiceLoopEnabled && (
                <button
                  type="button"
                  className={`voice-btn${wakeWordMode ? " voice-btn--conv" : ""}`}
                  onClick={toggleWakeWordMode}
                  title={wakeWordMode ? "Wake word ON" : "Wake word — say 'hey silvia'"}
                >
                  {wakeWordMode ? "◎ Wake ON" : "◎ Wake"}
                </button>
              )}

              {/* Push-to-talk */}
              {!voiceLoopEnabled && !wakeWordMode && (isRecording ? (
                <button type="button" className="voice-btn voice-btn--active" onClick={stopListening}>
                  ■ Stop
                </button>
              ) : (
                <button
                  type="button"
                  className="voice-btn"
                  onClick={startListening}
                  disabled={isProcessing || conversationMode || pending}
                >
                  {isProcessing ? "◌ …" : "◉ Mic"}
                </button>
              ))}

              {/* Conversation mode (push-to-talk with auto-relisten) */}
              {!voiceLoopEnabled && (
                <button
                  type="button"
                  className={`voice-btn${conversationMode ? " voice-btn--conv" : ""}`}
                  onClick={toggleConversationMode}
                  title={conversationMode ? "Conversation mode ON" : "Conversation mode — auto-relisten after responses"}
                >
                  {conversationMode ? "⟳ Conv ON" : "⟳ Conv"}
                </button>
              )}

              {/* Replay last response */}
              <button
                type="button"
                className="voice-btn"
                onClick={onReplayLast}
                disabled={isSpeaking}
                title="Replay last SILVIA response"
              >
                {isSpeaking ? "●" : "▶"}
              </button>

              {/* Voice settings */}
              <button
                type="button"
                className={`voice-btn voice-btn--sm${showVoiceSettings ? " voice-btn--conv" : ""}`}
                onClick={() => setShowVoiceSettings((s) => !s)}
                title="Voice settings"
              >
                ⚙
              </button>

              {/* STT diagnostics */}
              <button
                type="button"
                className="voice-btn voice-btn--sm"
                onClick={() => setShowDiag((s) => !s)}
                title="STT diagnostics"
                style={{ opacity: 0.7 }}
              >
                ⎔
              </button>

              <span className="voice-label">
                {voice?.stt_provider ? voice.stt_provider : "STT"}
                {" · "}
                {voice?.tts_provider ? voice.tts_provider : "TTS"}
              </span>
            </div>
            <span>{mode === "decision" ? "DECISION ENGINE" : "CONVERSATION"}</span>
          </div>
        </div>
        <button type="submit" disabled={pending || !draft.trim()}>
          {pending ? "●●●" : "EXEC"}
        </button>
      </form>
    </section>
  );
}
