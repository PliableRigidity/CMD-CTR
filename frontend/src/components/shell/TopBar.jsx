import { useEffect, useState } from "react";

function StatusDot({ active }) {
  return <span className={`status-dot ${active ? "is-active" : ""}`} />;
}

function SystemClock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const time = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(now);

  const date = new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(now);

  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <div className="system-clock">
      <p className="system-clock__label">Local Time</p>
      <div className="system-clock__time">{time}</div>
      <div className="system-clock__meta">
        <span>{date}</span>
        <span>{timezone}</span>
      </div>
    </div>
  );
}

export default function TopBar({ mode, modeReason, voice, devices, onModeChange, onOpenIntel }) {
  return (
    <header className="topbar panel">
      <div className="topbar__cluster topbar__cluster--left">
        <SystemClock />
      </div>

      <div className="topbar__identity">
        <p className="eyebrow">AI Operating System / Local-First</p>
        <h1>SILVIA</h1>
        <p className="topbar__subtext">
          Strategic Intelligence, Logistics, Voice &amp; Integrated Assistant
        </p>
        <div className="topbar__microcopy">
          <span>CORE NODE / OLLAMA</span>
          <span>MAGI ENGINE / STANDBY</span>
          <span>MISSION BUS / ACTIVE</span>
        </div>
      </div>

      <div className="topbar__controls">
        <div className="mode-toggle">
          <button
            className={mode === "conversation" ? "active" : ""}
            onClick={() => onModeChange("conversation")}
            type="button"
          >
            Conversation
          </button>
          <button
            className={mode === "decision" ? "active" : ""}
            onClick={() => onModeChange("decision")}
            type="button"
          >
            Decision
          </button>
        </div>

        <div className="status-group">
          <span><StatusDot active={voice?.available} /> Mic {voice?.listening ? "Hot" : "Standby"}</span>
          <span><StatusDot active /> Core Link Stable</span>
          <span><StatusDot active={devices.length > 0} /> {devices.length} Nodes</span>
        </div>
      </div>

      <div className="topbar__actions">
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="panel-button panel-button--accent" onClick={onOpenIntel}>
            Intel Board
          </button>
          <button
            type="button"
            className="panel-button"
            onClick={() => window.open("/voice", "_blank", "noopener,noreferrer")}
            title={`Voice: STT ${voice?.stt_available ? "ready" : "unavailable"} · TTS ${voice?.tts_available ? "ready" : "unavailable"}`}
            style={{ borderColor: voice?.stt_available && voice?.tts_available ? "rgba(198,242,238,0.25)" : "rgba(228,111,118,0.3)" }}
          >
            Voice {voice?.stt_available && voice?.tts_available ? "●" : "○"}
          </button>
        </div>
        <p className="mode-reason">Mode Logic: {modeReason}</p>
      </div>
    </header>
  );
}
