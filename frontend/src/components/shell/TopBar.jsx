import { useEffect, useState } from "react";

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
  }).format(now);

  const year = now.getFullYear();
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <div className="system-clock">
      <p className="system-clock__label">Local Time</p>
      <div className="system-clock__time">{time}</div>
      <div className="system-clock__meta">
        <span>{date} {year}</span>
        <span>{timezone}</span>
      </div>
    </div>
  );
}

function StatusDot({ active }) {
  return <span className={`status-dot${active ? " is-active" : ""}`} />;
}

export default function TopBar({ mode, modeReason, voice, devices, onModeChange, onOpenIntel }) {
  return (
    <header className="topbar panel">
      <div className="topbar__cluster topbar__cluster--left">
        <SystemClock />
      </div>

      <div className="topbar__identity">
        <p className="eyebrow">AI Operating System / Local-First Node</p>
        <h1>SILVIA</h1>
        <div className="topbar__microcopy">
          <span>Core · Ollama</span>
          <span>Magi · Standby</span>
          <span>Bus · Active</span>
        </div>
      </div>

      <div className="topbar__controls">
        <div className="mode-toggle">
          <button
            className={mode === "conversation" ? "active" : ""}
            onClick={() => onModeChange("conversation")}
            type="button"
          >
            Conv
          </button>
          <button
            className={mode === "decision" ? "active" : ""}
            onClick={() => onModeChange("decision")}
            type="button"
          >
            Council
          </button>
        </div>

        <div className="status-group">
          <span><StatusDot active={voice?.available} />{voice?.listening ? "Mic Hot" : "Mic Stby"}</span>
          <span><StatusDot active />Core Link</span>
          <span><StatusDot active={devices.length > 0} />{devices.length} Nodes</span>
        </div>
      </div>

      <div className="topbar__actions">
        <div style={{ display: "flex", gap: "6px" }}>
          <button
            type="button"
            className="panel-button panel-button--accent"
            onClick={onOpenIntel}
          >
            Intel Board
          </button>
          <button
            type="button"
            className="panel-button"
            onClick={() => window.open("/voice", "_blank", "noopener,noreferrer")}
            title={`STT ${voice?.stt_available ? "ready" : "unavail"} · TTS ${voice?.tts_available ? "ready" : "unavail"}`}
            style={{
              borderColor: voice?.stt_available && voice?.tts_available
                ? "rgba(0,255,136,0.35)"
                : "rgba(255,59,59,0.40)",
              color: voice?.stt_available && voice?.tts_available
                ? "var(--success)"
                : "var(--danger)",
            }}
          >
            Voice {voice?.stt_available && voice?.tts_available ? "●" : "○"}
          </button>
        </div>
        <p className="mode-reason">{modeReason}</p>
      </div>
    </header>
  );
}
