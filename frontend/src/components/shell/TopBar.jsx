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

const PRIMARY_NAV = [
  { label: "Assistant",  href: "/",         self: true },
  { label: "Projects",   href: "/workspace" },
  { label: "Hardware",   href: "/hardware" },
];

const ADVANCED_NAV = [
  { label: "Graph",      href: "/knowledge" },
  { label: "Memory",     href: "/memory" },
  { label: "Twin",       href: "/workspace" },
  { label: "Planner",    href: "/planner" },
  { label: "Workflows",  href: "/workflows" },
  { label: "Brain63",    href: "/brain63" },
  { label: "Voice",      href: "/voice" },
];

export default function TopBar({ mode, modeReason, voice, devices, onModeChange, onOpenIntel, onOpenHardware, onOpenSettings }) {
  const [devMode, setDevMode] = useState(() => localStorage.getItem("silvia_dev_mode") === "true");

  function toggleDevMode() {
    const next = !devMode;
    setDevMode(next);
    localStorage.setItem("silvia_dev_mode", String(next));
  }

  function navTo(item) {
    if (item.self) return;
    window.open(`${window.location.origin}${item.href}`, "_blank", "noopener,noreferrer");
  }

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
        <div className="topbar__nav-row">
          {/* Primary navigation */}
          {PRIMARY_NAV.map((item) => (
            <button
              key={item.label}
              type="button"
              className={`panel-button${item.self ? " panel-button--accent" : ""}`}
              onClick={() => item.self ? null : navTo(item)}
              style={item.self ? { cursor: "default" } : {}}
            >
              {item.label}
            </button>
          ))}

          {/* Separator */}
          <span className="topbar__nav-sep" />

          {/* Intel (optional, always visible) */}
          <button type="button" className="panel-button" onClick={onOpenIntel}>Intel</button>

          {/* Settings */}
          <button
            type="button"
            className="panel-button"
            onClick={onOpenSettings}
            title="API Key / Authentication settings"
            style={{ fontSize: "0.85rem", padding: "4px 8px", opacity: 0.7 }}
          >
            ⚙
          </button>

          {/* Dev Mode toggle */}
          <button
            type="button"
            className={`panel-button topbar__dev-toggle${devMode ? " topbar__dev-toggle--on" : ""}`}
            onClick={toggleDevMode}
            title={devMode ? "Developer Mode ON — click to hide advanced boards" : "Developer Mode OFF — click to show advanced boards"}
          >
            {devMode ? "◆ Dev" : "◇ Dev"}
          </button>

          {/* Advanced navigation (only when dev mode is on) */}
          {devMode && ADVANCED_NAV.map((item) => (
            <button
              key={item.label}
              type="button"
              className="panel-button panel-button--dev"
              onClick={() => navTo(item)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <p className="mode-reason">{modeReason}</p>
      </div>
    </header>
  );
}
