import { useState } from "react";

const QUICK_APPS = [
  { label: "Chrome",   alias: "chrome" },
  { label: "Spotify",  alias: "spotify" },
  { label: "Terminal", alias: "terminal" },
  { label: "VS Code",  alias: "vscode" },
  { label: "GitHub",   alias: "github" },
  { label: "Discord",  alias: "discord" },
];

export default function ActionShortcutsPanel({ actions, audio, onRunAction, onRunAliasAction, onAudioAction }) {
  const [query, setQuery] = useState("");

  async function handleLaunch(alias) {
    await onRunAliasAction(alias);
  }

  async function handleSearch(e) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    await onRunAliasAction(q);
    setQuery("");
  }

  const filteredQuick = query
    ? QUICK_APPS.filter(
        (a) =>
          a.label.toLowerCase().includes(query.toLowerCase()) ||
          a.alias.toLowerCase().includes(query.toLowerCase())
      )
    : QUICK_APPS;

  const filteredActions = actions.filter(
    (a) => !query || a.label.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Control Registry</p>
          <h2>Launcher</h2>
        </div>
      </div>

      <form className="launcher-search" onSubmit={handleSearch}>
        <input
          className="launcher-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="open…"
        />
        {query && (
          <button type="submit" className="panel-button" style={{ flexShrink: 0 }}>Run</button>
        )}
      </form>

      <div className="launcher-grid">
        {filteredQuick.map((app) => (
          <button
            key={app.alias}
            type="button"
            className="launcher-btn"
            onClick={() => handleLaunch(app.alias)}
          >
            {app.label}
          </button>
        ))}
        {filteredActions.map((action) => (
          <button
            key={action.id}
            type="button"
            className="launcher-btn"
            onClick={() => onRunAction(action)}
            title={action.description}
          >
            {action.label}
          </button>
        ))}
      </div>

      <div className="audio-bar">
        <div className="audio-bar__group">
          <button type="button" onClick={() => onAudioAction("previous")} title="Previous">◄</button>
          <button type="button" onClick={() => onAudioAction("play_pause")} title="Play/Pause">●</button>
          <button type="button" onClick={() => onAudioAction("next")} title="Next">►</button>
        </div>
        <span className="audio-bar__vol">
          {audio?.volume_percent != null ? `${audio.volume_percent}%` : "—"}
        </span>
        <div className="audio-bar__group">
          <button type="button" onClick={() => onAudioAction("down")} title="Volume down">−</button>
          <button type="button" onClick={() => onAudioAction("up")} title="Volume up">+</button>
          <button
            type="button"
            onClick={() => onAudioAction("mute")}
            title={audio?.muted ? "Unmute" : "Mute"}
          >
            {audio?.muted ? "Un" : "Mute"}
          </button>
        </div>
      </div>
    </section>
  );
}
