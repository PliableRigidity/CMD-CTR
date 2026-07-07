const SEVERITY_COLORS = {
  critical: "#ff3b3b",
  high:     "#f5a623",
  medium:   "#e8d44d",
  low:      "#00e5ff",
};

const CATEGORY_LABELS = {
  tech:        "TECH",
  science:     "SCI",
  politics:    "POL",
  conflict:    "CONFLICT",
  economics:   "ECON",
  health:      "HEALTH",
  environment: "ENV",
  disaster:    "DISASTER",
  culture:     "CULTURE",
  sports:      "SPORTS",
};

function timeAgo(ts) {
  if (!ts) return "";
  const ms = typeof ts === "number" ? ts : parseInt(ts, 10);
  if (isNaN(ms)) return "";
  const diff = Date.now() - ms;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

function IntelEventCard({ event, selected, onClick }) {
  const sev = (event.board_priority || event.priority || "low").toLowerCase();
  const sevColor = SEVERITY_COLORS[sev] || SEVERITY_COLORS.low;
  const catLabel = CATEGORY_LABELS[event.category] || (event.category || "").toUpperCase().slice(0, 8);

  return (
    <div
      className={`intel-event-card${selected ? " intel-event-card--selected" : ""}`}
      style={{ borderLeftColor: sevColor }}
      onClick={onClick}
    >
      <div className="intel-event-card-header">
        <span className="intel-event-severity" style={{ color: sevColor }}>
          {sev.toUpperCase()}
        </span>
        <span className="intel-event-category">{catLabel}</span>
        {event.primary_country && (
          <span className="intel-event-country">{event.primary_country}</span>
        )}
      </div>
      <p className="intel-event-title">{event.title}</p>
      {event.assessment && !selected && (
        <p className="intel-event-preview">{event.assessment}</p>
      )}
      <div className="intel-event-meta">
        <span>{event.source_name || ""}</span>
        <span>{timeAgo(event.published_at || event.time)}</span>
      </div>
    </div>
  );
}

function EarthquakeCard({ eq, selected, onClick }) {
  const mag = eq.mag || 0;
  const sev = mag >= 6 ? "critical" : mag >= 4.5 ? "high" : mag >= 3 ? "medium" : "low";
  const sevColor = SEVERITY_COLORS[sev];

  return (
    <div
      className={`intel-event-card${selected ? " intel-event-card--selected" : ""}`}
      style={{ borderLeftColor: sevColor }}
      onClick={onClick}
    >
      <div className="intel-event-card-header">
        <span className="intel-event-severity" style={{ color: sevColor }}>
          M{mag.toFixed(1)}
        </span>
        <span className="intel-event-category">SEISMIC</span>
      </div>
      <p className="intel-event-title">{eq.title}</p>
      <div className="intel-event-meta">
        <span>USGS</span>
        <span>{timeAgo(eq.time)}</span>
      </div>
    </div>
  );
}

function DetailView({ item, kind, onClose }) {
  if (!item) return null;

  const isEvent = kind === "event";
  const sev = isEvent
    ? (item.board_priority || item.priority || "low").toLowerCase()
    : (item.mag >= 6 ? "critical" : item.mag >= 4.5 ? "high" : item.mag >= 3 ? "medium" : "low");
  const sevColor = SEVERITY_COLORS[sev];

  return (
    <div className="intel-detail">
      <div className="intel-detail-header">
        <span className="intel-detail-sev" style={{ color: sevColor }}>{sev.toUpperCase()}</span>
        <button className="intel-panel-close" onClick={onClose}>×</button>
      </div>

      <h3 className="intel-detail-title">{isEvent ? item.title : item.title}</h3>

      {isEvent && item.assessment && (
        <div className="intel-detail-section">
          <p className="intel-section-label">ASSESSMENT</p>
          <p className="intel-detail-text">{item.assessment}</p>
        </div>
      )}

      {isEvent && item.prediction && (
        <div className="intel-detail-section">
          <p className="intel-section-label">PREDICTION</p>
          <p className="intel-detail-text">{item.prediction}</p>
        </div>
      )}

      {isEvent && item.recommendation && (
        <div className="intel-detail-section">
          <p className="intel-section-label" style={{ color: "var(--warning)" }}>RECOMMENDED ACTION</p>
          <p className="intel-detail-text" style={{ color: "var(--warning)" }}>{item.recommendation}</p>
        </div>
      )}

      {!isEvent && (
        <div className="intel-detail-section">
          <p className="intel-section-label">SEISMIC DATA</p>
          <p className="intel-detail-text">
            Magnitude {(item.mag || 0).toFixed(1)} — {item.title}
          </p>
          {item.time && (
            <p className="intel-detail-text" style={{ color: "var(--text-dim)" }}>
              {new Date(parseInt(item.time, 10)).toLocaleString()}
            </p>
          )}
        </div>
      )}

      {isEvent && (item.source_url || item.url) && (
        <div className="intel-detail-section">
          <a
            href={item.source_url || item.url}
            target="_blank"
            rel="noreferrer"
            className="intel-detail-link"
          >
            Open source ↗
          </a>
        </div>
      )}
    </div>
  );
}

export default function IntelBriefingPanel({
  events = [],
  earthquakes = [],
  selectedId,
  onSelect,
  collapsed,
  onToggleCollapse,
}) {
  if (collapsed) {
    return (
      <button className="intel-panel-toggle intel-panel-toggle--right" onClick={onToggleCollapse}>
        ‹ BRIEFING
      </button>
    );
  }

  const selectedEvent = events.find((e) => e.id === selectedId);
  const selectedQuake = earthquakes.find((e) => e.id === selectedId);
  const selectedItem = selectedEvent || selectedQuake;
  const selectedKind = selectedEvent ? "event" : "earthquake";

  // Summary counts
  const critCount = events.filter(
    (e) => (e.board_priority || e.priority || "").toLowerCase() === "critical"
  ).length + earthquakes.filter((e) => (e.mag || 0) >= 6).length;

  const highCount = events.filter(
    (e) => (e.board_priority || e.priority || "").toLowerCase() === "high"
  ).length + earthquakes.filter((e) => (e.mag || 0) >= 4.5 && (e.mag || 0) < 6).length;

  const totalCount = events.length + earthquakes.length;

  return (
    <aside className="intel-briefing-panel">
      <div className="intel-panel-header">
        <span className="intel-panel-eyebrow">INTEL BRIEFING</span>
        <button className="intel-panel-close" onClick={onToggleCollapse}>›</button>
      </div>

      {/* Summary */}
      <div className="intel-briefing-summary">
        <div className="intel-briefing-stat">
          <span className="intel-briefing-stat-value" style={{ color: "#ff3b3b" }}>{critCount}</span>
          <span className="intel-briefing-stat-label">CRITICAL</span>
        </div>
        <div className="intel-briefing-stat">
          <span className="intel-briefing-stat-value" style={{ color: "#f5a623" }}>{highCount}</span>
          <span className="intel-briefing-stat-label">HIGH</span>
        </div>
        <div className="intel-briefing-stat">
          <span className="intel-briefing-stat-value">{totalCount}</span>
          <span className="intel-briefing-stat-label">TOTAL</span>
        </div>
      </div>

      {/* Detail view when something is selected */}
      {selectedItem && (
        <DetailView
          item={selectedItem}
          kind={selectedKind}
          onClose={() => onSelect(null)}
        />
      )}

      {/* Feed list */}
      <div className="intel-briefing-feed">
        {events.length === 0 && earthquakes.length === 0 && (
          <p className="intel-empty">No intelligence data loaded</p>
        )}

        {events.map((ev) => (
          <IntelEventCard
            key={ev.id}
            event={ev}
            selected={selectedId === ev.id}
            onClick={() => onSelect(ev.id, "event")}
          />
        ))}

        {earthquakes.length > 0 && (
          <>
            <p className="intel-section-label" style={{ padding: "8px 0 4px" }}>SEISMIC ACTIVITY</p>
            {earthquakes.slice(0, 10).map((eq) => (
              <EarthquakeCard
                key={eq.id}
                eq={eq}
                selected={selectedId === eq.id}
                onClick={() => onSelect(eq.id, "earthquake")}
              />
            ))}
          </>
        )}
      </div>

      <div className="intel-panel-footer">
        <span>SILVIA INTEL ENGINE</span>
        <span>LIVE</span>
      </div>
    </aside>
  );
}
