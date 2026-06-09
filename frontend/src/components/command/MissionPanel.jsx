import { useEffect, useState } from "react";
import { fetchMissions } from "../../lib/api";

const STATUS_CLASS = { active: "active", monitoring: "monitoring", paused: "paused" };
const STATUS_LABEL = { active: "Active", monitoring: "Monitor", paused: "Paused" };

export default function MissionPanel({ mode, onOpenIntel }) {
  const [missions, setMissions] = useState([]);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    fetchMissions()
      .then(setMissions)
      .catch(() => {});
  }, []);

  return (
    <section className="panel mission-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Mission Layer / Ops Context</p>
          <h2>Active Missions</h2>
        </div>
        <span
          className={`state-pill state-pill--${mode === "decision" ? "busy" : "idle"}`}
          style={{ fontSize: "0.6rem", padding: "2px 8px" }}
        >
          {mode === "decision" ? "Council" : "Direct"}
        </span>
      </div>

      <div className="mission-strip">
        {missions.map((m) => (
          <div key={m.id}>
            <button
              type="button"
              className="mission-row"
              onClick={() => setExpanded(expanded === m.id ? null : m.id)}
            >
              <span className={`mission-dot mission-dot--${STATUS_CLASS[m.status] ?? "active"}`} />
              <span className="mission-code">{m.code}</span>
              <span className="mission-name">{m.name}</span>
              <span className="mission-status">{STATUS_LABEL[m.status] ?? m.status}</span>
            </button>
            {expanded === m.id && (
              <p className="mission-desc">{m.description}</p>
            )}
          </div>
        ))}
      </div>

      <button type="button" className="panel-button intel-link-btn" onClick={onOpenIntel}>
        Intel Board →
      </button>
    </section>
  );
}
