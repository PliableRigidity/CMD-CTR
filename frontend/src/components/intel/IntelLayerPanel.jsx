const LAYERS = [
  { id: "global",      label: "Global Events",     color: "#00e5ff" },
  { id: "tech",        label: "AI / Technology",    color: "#60a5fa" },
  { id: "cyber",       label: "Cybersecurity",      color: "#c084fc" },
  { id: "engineering", label: "Engineering",         color: "#f5a623" },
  { id: "seismic",     label: "Seismic / Disaster",  color: "#ff3b3b" },
  { id: "weather",     label: "Weather",             color: "#4ade80" },
  { id: "supply",      label: "Supply Chain",        color: "#fb923c" },
];

const SEVERITIES = [
  { id: "all",      label: "ALL" },
  { id: "critical", label: "CRITICAL", color: "#ff3b3b" },
  { id: "high",     label: "HIGH",     color: "#f5a623" },
  { id: "medium",   label: "MEDIUM",   color: "#e8d44d" },
  { id: "low",      label: "LOW",      color: "#00e5ff" },
];

const WINDOWS = [
  { id: "1h",   label: "1H"   },
  { id: "6h",   label: "6H"   },
  { id: "24h",  label: "24H"  },
  { id: "7d",   label: "7D"   },
  { id: "all",  label: "ALL"  },
  { id: "live", label: "LIVE" },
];

export default function IntelLayerPanel({
  activeLayers, onToggleLayer,
  severity, onSeverityChange,
  timeWindow, onTimeWindowChange,
  stats = {},
}) {
  return (
    <aside className="iv4-layers">
      <div className="iv4-layers-head">
        <span className="iv4-section-title">INTEL LAYERS</span>
      </div>

      <div className="iv4-layers-list">
        {LAYERS.map((l) => (
          <label key={l.id} className="iv4-layer-row">
            <input
              type="checkbox"
              checked={activeLayers.includes(l.id)}
              onChange={() => onToggleLayer(l.id)}
            />
            <span className="iv4-layer-dot" style={{ background: l.color }} />
            <span className="iv4-layer-name">{l.label}</span>
            <span className="iv4-layer-ct">{stats[l.id] ?? 0}</span>
          </label>
        ))}
      </div>

      <div className="iv4-filter-section">
        <p className="iv4-filter-label">SEVERITY FILTER</p>
        <div className="iv4-chips">
          {SEVERITIES.map((s) => (
            <button
              key={s.id}
              className={`iv4-chip${severity === s.id ? " iv4-chip--on" : ""}`}
              style={severity === s.id && s.color ? { borderColor: s.color, color: s.color } : {}}
              onClick={() => onSeverityChange(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="iv4-filter-section">
        <p className="iv4-filter-label">TIME WINDOW</p>
        <div className="iv4-chips">
          {WINDOWS.map((w) => (
            <button
              key={w.id}
              className={`iv4-chip${timeWindow === w.id ? " iv4-chip--on" : ""}`}
              onClick={() => onTimeWindowChange(w.id)}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <div className="iv4-legend-section">
        <p className="iv4-filter-label">MARKER LEGEND</p>
        <div className="iv4-legend">
          <div className="iv4-legend-item"><span className="iv4-lg-dot" style={{ background: "#ff3b3b", boxShadow: "0 0 6px #ff3b3b" }} /> Critical — pulsing ring</div>
          <div className="iv4-legend-item"><span className="iv4-lg-dot" style={{ background: "#f5a623" }} /> High — orange ring/dot</div>
          <div className="iv4-legend-item"><span className="iv4-lg-dot" style={{ background: "#e8d44d" }} /> Medium — yellow ring/dot</div>
          <div className="iv4-legend-item"><span className="iv4-lg-dot" style={{ background: "#00e5ff" }} /> Low — cyan dot</div>
          <div className="iv4-legend-item"><span className="iv4-lg-dot" style={{ background: "#f5a623", borderRadius: "1px", transform: "rotate(45deg)", width: 8, height: 8 }} /> Project — gold diamond</div>
          <div className="iv4-legend-item"><span className="iv4-lg-dot" style={{ background: "#00ff88", borderRadius: "2px" }} /> Fleet / Node — green square</div>
          <div className="iv4-legend-item"><span className="iv4-lg-dot" style={{ background: "#60a5fa", borderRadius: "1px" }} /> Engineering — blue hexagon</div>
        </div>
      </div>
    </aside>
  );
}
