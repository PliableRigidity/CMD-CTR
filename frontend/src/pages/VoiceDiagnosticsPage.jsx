import { useEffect, useRef, useState } from "react";
import { fetchVoiceDiagnostics, transcribeAudio, synthesizeSpeech } from "../lib/api";

const STATUS_COLOR = {
  ready: "var(--accent-warm)",
  unavailable: "var(--danger)",
  unknown: "var(--muted)",
  ok: "var(--accent-warm)",
  error: "var(--danger)",
};

function StatusDot({ status }) {
  const color = STATUS_COLOR[status] || "var(--muted)";
  return (
    <span
      style={{
        display: "inline-block",
        width: 9,
        height: 9,
        borderRadius: "50%",
        background: color,
        marginRight: 8,
        boxShadow: status === "ready" || status === "ok" ? `0 0 6px ${color}` : "none",
        flexShrink: 0,
      }}
    />
  );
}

function Row({ label, status, detail, mono }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "7px 0", borderBottom: "1px solid rgba(114,210,222,0.07)" }}>
      <StatusDot status={status} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text)" }}>{label}</div>
        {detail && (
          <div style={{ fontSize: "0.71rem", color: "var(--muted)", marginTop: 2, fontFamily: mono ? "'JetBrains Mono','Courier New',monospace" : undefined, wordBreak: "break-all" }}>
            {detail}
          </div>
        )}
      </div>
      <span style={{ fontSize: "0.67rem", textTransform: "uppercase", letterSpacing: "0.1em", color: STATUS_COLOR[status] || "var(--muted)", flexShrink: 0 }}>
        {status}
      </span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <p style={{ margin: "0 0 10px", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.18em", color: "var(--accent)" }}>{title}</p>
      <div style={{ background: "rgba(7,15,24,0.88)", border: "1px solid rgba(114,210,222,0.12)", borderRadius: 14, padding: "4px 16px" }}>
        {children}
      </div>
    </div>
  );
}

export default function VoiceDiagnosticsPage() {
  const [diag, setDiag] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Mic test
  const [micStatus, setMicStatus] = useState("idle"); // idle | checking | granted | denied
  const [micLabel, setMicLabel] = useState(null);
  const [mimeType, setMimeType] = useState(null);

  // STT test
  const [sttStatus, setSttStatus] = useState("idle");
  const [lastTranscription, setLastTranscription] = useState(null);
  const [lastTranscriptionMeta, setLastTranscriptionMeta] = useState(null);
  const [sttError, setSttError] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const [recording, setRecording] = useState(false);

  // TTS test
  const [ttsStatus, setTtsStatus] = useState("idle");
  const [lastAudioBytes, setLastAudioBytes] = useState(null);
  const [ttsError, setTtsError] = useState(null);
  const [playbackStatus, setPlaybackStatus] = useState("idle");

  // Playback test
  const [playStatus, setPlayStatus] = useState("idle");

  useEffect(() => {
    fetchVoiceDiagnostics()
      .then(setDiag)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function checkMic() {
    setMicStatus("checking");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const tracks = stream.getAudioTracks();
      setMicLabel(tracks[0]?.label || "default device");

      // Detect supported recording format
      const formats = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
      const supported = formats.filter((f) => MediaRecorder.isTypeSupported(f));
      setMimeType(supported[0] || "browser default");

      stream.getTracks().forEach((t) => t.stop());
      setMicStatus("granted");
    } catch (e) {
      setMicStatus("denied");
      setMicLabel(e.message);
    }
  }

  async function startSttTest() {
    setSttStatus("recording");
    setSttError(null);
    setLastTranscription(null);
    setLastTranscriptionMeta(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const formats = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
      const fmt = formats.find((f) => MediaRecorder.isTypeSupported(f)) || "";
      const recorder = fmt ? new MediaRecorder(stream, { mimeType: fmt }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        setSttStatus("transcribing");
        const actualMime = recorder.mimeType || fmt || "audio/webm";
        const ext = actualMime.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(chunksRef.current, { type: actualMime });
        try {
          const result = await transcribeAudio(blob, actualMime);
          setLastTranscription(result.text || result.message || "(empty — no speech detected)");
          setLastTranscriptionMeta(result.diagnostics || null);
          setSttStatus("ok");
        } catch (e) {
          setSttError(e.message);
          setSttStatus("error");
        }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch (e) {
      setSttError(e.message);
      setSttStatus("error");
      setRecording(false);
    }
  }

  function stopSttTest() {
    mediaRecorderRef.current?.stop();
  }

  async function runTtsTest() {
    setTtsStatus("synthesizing");
    setTtsError(null);
    setLastAudioBytes(null);
    try {
      const buffer = await synthesizeSpeech("SILVIA voice pipeline operational. All systems nominal.");
      setLastAudioBytes(buffer.byteLength);
      setTtsStatus("ok");
      setPlaybackStatus("idle");
    } catch (e) {
      setTtsError(e.message);
      setTtsStatus("error");
    }
  }

  async function playLastTts() {
    if (!lastAudioBytes) return;
    setPlayStatus("playing");
    try {
      const buffer = await synthesizeSpeech("SILVIA voice pipeline operational. All systems nominal.");
      const ctx = new AudioContext();
      const decoded = await ctx.decodeAudioData(buffer);
      const src = ctx.createBufferSource();
      src.buffer = decoded;
      src.connect(ctx.destination);
      src.onended = () => { ctx.close(); setPlayStatus("ok"); };
      src.start();
    } catch (e) {
      setPlayStatus("error");
    }
  }

  const panelStyle = {
    maxWidth: 760,
    margin: "0 auto",
    padding: "28px 24px",
    fontFamily: "'Segoe UI','Helvetica Neue',sans-serif",
    color: "var(--text)",
  };

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(160deg,#03060b 0%,#050b12 42%,#08111b 100%)", padding: "0 16px 40px" }}>
      <div style={panelStyle}>
        <div style={{ marginBottom: 28 }}>
          <p style={{ margin: "0 0 6px", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.2em", color: "var(--accent)" }}>SILVIA / Voice Pipeline</p>
          <h1 style={{ margin: 0, fontSize: "1.9rem", color: "var(--text)" }}>Voice Diagnostics</h1>
          <p style={{ margin: "8px 0 0", color: "var(--muted)", fontSize: "0.87rem" }}>
            Full pipeline audit — microphone → STT → TTS → playback
          </p>
          <div style={{ display: "flex", gap: 12, marginTop: 14 }}>
            <a href="/" style={{ color: "var(--accent)", fontSize: "0.8rem", textDecoration: "none" }}>← Back to Command Center</a>
            <button
              onClick={() => { setLoading(true); fetchVoiceDiagnostics().then(setDiag).catch((e) => setError(e.message)).finally(() => setLoading(false)); }}
              style={{ background: "rgba(114,210,222,0.08)", border: "1px solid rgba(114,210,222,0.18)", color: "var(--text)", borderRadius: 8, padding: "4px 12px", cursor: "pointer", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.08em" }}
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Backend diagnostics */}
        <Section title="Backend / Provider Status">
          {loading && <div style={{ padding: "12px 0", color: "var(--muted)", fontSize: "0.8rem" }}>Loading…</div>}
          {error && <Row label="Backend unreachable" status="error" detail={error} />}
          {diag && (
            <>
              <Row
                label="STT — faster-whisper"
                status={diag.stt.status}
                detail={`Model: ${diag.stt.model_size} · ${diag.stt.detail}`}
              />
              <Row
                label="TTS — Piper binary"
                status={diag.tts.binary_found ? "ready" : "unavailable"}
                detail={diag.tts.binary_path || "piper not found in PATH"}
                mono
              />
              <Row
                label="TTS — Piper model"
                status={diag.tts.model_exists ? "ready" : "unavailable"}
                detail={diag.tts.model_path}
                mono
              />
            </>
          )}
        </Section>

        {/* Config snapshot */}
        {diag && (
          <Section title="Configuration">
            <Row label="Whisper model size" status="ok" detail={diag.config.whisper_model_size} mono />
            <Row label="Piper model path" status={diag.tts.model_exists ? "ok" : "error"} detail={diag.config.piper_model_path} mono />
            <Row label="Piper config" status="ok" detail={diag.config.piper_config_path} mono />
            <Row label="Piper CUDA" status="ok" detail={String(diag.config.piper_use_cuda)} mono />
          </Section>
        )}

        {/* Microphone */}
        <Section title="Microphone">
          <Row
            label="Microphone access"
            status={micStatus === "granted" ? "ok" : micStatus === "denied" ? "error" : "unknown"}
            detail={micLabel || "Click Test to request permission"}
          />
          {micStatus === "granted" && (
            <Row label="Best recording format" status="ok" detail={mimeType} mono />
          )}
          <div style={{ padding: "10px 0 6px" }}>
            <button onClick={checkMic} style={btnStyle}>
              {micStatus === "checking" ? "Checking…" : "Test Microphone"}
            </button>
          </div>
        </Section>

        {/* STT test */}
        <Section title="Speech-to-Text Test">
          <Row
            label="STT status"
            status={sttStatus === "ok" ? "ok" : sttStatus === "error" ? "error" : sttStatus === "idle" ? "unknown" : "ready"}
            detail={sttError || (sttStatus === "recording" ? "Recording… click Stop when done" : sttStatus === "transcribing" ? "Sending to Whisper…" : "Click Start to record a test phrase")}
          />
          {lastTranscription != null && (
            <Row label="Last transcription" status="ok" detail={`"${lastTranscription}"`} />
          )}
          {lastTranscriptionMeta && (
            <>
              <Row label="Audio blob" status="ok" detail={`${lastTranscriptionMeta.audio_size_bytes} bytes · ${lastTranscriptionMeta.mime_type || "unknown MIME"} · ${lastTranscriptionMeta.detected_extension}`} mono />
              <Row label="Audio analysis" status={lastTranscriptionMeta.speech_detected ? "ok" : "error"} detail={`Duration ${lastTranscriptionMeta.duration_seconds}s · RMS ${lastTranscriptionMeta.rms_db} dB · Peak ${lastTranscriptionMeta.peak_db} dB · Speech ${lastTranscriptionMeta.speech_detected ? "detected" : "not detected"}`} />
              <Row label="Model output" status="ok" detail={`Raw "${lastTranscriptionMeta.raw_transcript || ""}" · Final "${lastTranscriptionMeta.final_transcript || ""}"`} />
              <Row label="Confidence" status="ok" detail={`Lang ${lastTranscriptionMeta.language || "n/a"} (${lastTranscriptionMeta.language_probability ?? "n/a"}) · Confidence ${lastTranscriptionMeta.transcription_confidence ?? "n/a"} · No-speech ${lastTranscriptionMeta.no_speech_probability ?? "n/a"} · Fallback ${lastTranscriptionMeta.fallback_used ? "yes" : "no"}`} />
            </>
          )}
          <div style={{ padding: "10px 0 6px", display: "flex", gap: 10 }}>
            {!recording ? (
              <button onClick={startSttTest} style={btnStyle}>Start Recording</button>
            ) : (
              <button onClick={stopSttTest} style={{ ...btnStyle, borderColor: "rgba(228,111,118,0.4)", color: "var(--danger)", background: "rgba(228,111,118,0.08)" }}>
                Stop & Transcribe
              </button>
            )}
          </div>
        </Section>

        {/* TTS test */}
        <Section title="Text-to-Speech Test">
          <Row
            label="TTS status"
            status={ttsStatus === "ok" ? "ok" : ttsStatus === "error" ? "error" : "unknown"}
            detail={ttsError || (lastAudioBytes ? `Generated ${lastAudioBytes.toLocaleString()} bytes of WAV audio` : "Click Synthesize to test Piper")}
          />
          {lastAudioBytes && (
            <Row
              label="Playback"
              status={playStatus === "ok" ? "ok" : playStatus === "error" ? "error" : "unknown"}
              detail={playStatus === "playing" ? "Playing…" : playStatus === "ok" ? "Played successfully" : playStatus === "error" ? "Playback error — check browser audio" : "Click Play to verify output"}
            />
          )}
          <div style={{ padding: "10px 0 6px", display: "flex", gap: 10 }}>
            <button onClick={runTtsTest} style={btnStyle} disabled={ttsStatus === "synthesizing"}>
              {ttsStatus === "synthesizing" ? "Synthesizing…" : "Synthesize Test Phrase"}
            </button>
            {lastAudioBytes && (
              <button onClick={playLastTts} style={btnStyle} disabled={playStatus === "playing"}>
                {playStatus === "playing" ? "Playing…" : "Play Audio"}
              </button>
            )}
          </div>
        </Section>

        {/* Browser info */}
        <Section title="Browser Audio Environment">
          <BrowserInfo />
        </Section>
      </div>
    </div>
  );
}

function BrowserInfo() {
  const [info, setInfo] = useState(null);

  useEffect(() => {
    const formats = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
      "audio/wav",
      "audio/mp4",
    ];
    const supported = formats.filter((f) => MediaRecorder.isTypeSupported(f));
    const hasMediaDevices = !!navigator.mediaDevices?.getUserMedia;
    const hasAudioContext = !!(window.AudioContext || window.webkitAudioContext);
    const hasSpeechRecognition = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    setInfo({ supported, hasMediaDevices, hasAudioContext, hasSpeechRecognition });
  }, []);

  if (!info) return <div style={{ padding: "8px 0", color: "var(--muted)", fontSize: "0.8rem" }}>Loading…</div>;

  return (
    <>
      <Row label="MediaDevices.getUserMedia" status={info.hasMediaDevices ? "ok" : "error"} detail={info.hasMediaDevices ? "available" : "not available (need HTTPS or localhost)"} />
      <Row label="AudioContext" status={info.hasAudioContext ? "ok" : "error"} detail={info.hasAudioContext ? "available" : "not available"} />
      <Row label="Web Speech API (fallback)" status={info.hasSpeechRecognition ? "ok" : "unknown"} detail={info.hasSpeechRecognition ? "available (not used — Whisper preferred)" : "not available in this browser"} />
      <Row
        label="Supported recording formats"
        status={info.supported.length > 0 ? "ok" : "error"}
        detail={info.supported.length > 0 ? info.supported.join(", ") : "none — cannot record audio"}
        mono
      />
    </>
  );
}

const btnStyle = {
  background: "rgba(114,210,222,0.08)",
  border: "1px solid rgba(114,210,222,0.18)",
  color: "var(--text)",
  borderRadius: 10,
  padding: "8px 16px",
  cursor: "pointer",
  fontSize: "0.77rem",
  textTransform: "uppercase",
  letterSpacing: "0.08em",
};
