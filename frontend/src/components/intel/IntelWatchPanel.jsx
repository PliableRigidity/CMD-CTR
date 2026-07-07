const SEV_COLOR = { critical: "#ff3b3b", high: "#f5a623", medium: "#e8d44d", low: "#00e5ff" };
const SEV_ICON  = { critical: "●", high: "◆", medium: "◆", low: "◇" };

function timeAgo(ts) {
  if (!ts) return "";
  const ms = typeof ts === "number" ? ts : parseInt(ts, 10);
  if (isNaN(ms) || ms === 0) return "";
  const diff = Date.now() - ms;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

function ImpactCard({ event }) {
  const s = (event.board_priority || event.priority || "low").toLowerCase();
  const color = SEV_COLOR[s] || SEV_COLOR.low;
  const icon = SEV_ICON[s] || "·";
  const cat = (event.category || "").replace(/_/g, " ");

  return (
    <div className="iv4-impact-card">
      <div className="iv4-impact-left">
        <span className="iv4-impact-icon" style={{ color }}>{icon}</span>
      </div>
      <div className="iv4-impact-body">
        <p className="iv4-impact-title">{event.title}</p>
        <p className="iv4-impact-cat">{cat}{event.primary_country ? ` · ${event.primary_country}` : ""}</p>
      </div>
      <div className="iv4-impact-right">
        {event._affects && (
          <span className="iv4-impact-affects">Affects <strong>{event._affects}</strong></span>
        )}
        {!event._affects && (
          <span className="iv4-impact-time">{timeAgo(event.published_at)}</span>
        )}
      </div>
    </div>
  );
}

export default function IntelWatchPanel({
  events = [],
  earthquakes = [],
  watchAlerts = [],
  stats = {},
}) {
  const critCount = stats.critical || 0;
  const highCount = stats.high || 0;
  const totalCount = stats.total || 0;

  // Top impacts: critical and high events
  const topImpacts = events
    .filter((e) => {
      const s = (e.board_priority || e.priority || "low").toLowerCase();
      return s === "critical" || s === "high";
    })
    .slice(0, 6);

  return (
    <aside className="iv4-watch">
      <div className="iv4-watch-head">
        <span className="iv4-section-title">WATCH OFFICER BRIEFING</span>
        <span className="iv4-ai-badge">AI</span>
      </div>

      {/* Daily Brief */}
      <div className="iv4-brief">
        <div className="iv4-brief-dot" />
        <div>
          <p className="iv4-brief-label">DAILY BRIEF</p>
          <p className="iv4-brief-text">Here's what matters today.</p>
        </div>
      </div>

      {/* Severity Stats */}
      <div className="iv4-watch-stats">
        <div className="iv4-watch-stat">
          <span className="iv4-watch-stat-val" style={{ color: "#ff3b3b" }}>{critCount}</span>
          <span className="iv4-watch-stat-lbl">CRITICAL</span>
        </div>
        <div className="iv4-watch-stat">
          <span className="iv4-watch-stat-val" style={{ color: "#f5a623" }}>{highCount}</span>
          <span className="iv4-watch-stat-lbl">HIGH</span>
        </div>
        <div className="iv4-watch-stat">
          <span className="iv4-watch-stat-val">{totalCount}</span>
          <span className="iv4-watch-stat-lbl">TOTAL</span>
        </div>
      </div>

      {/* Top Impacts */}
      <div className="iv4-watch-section">
        <p className="iv4-filter-label">TOP IMPACTS</p>
        <div className="iv4-impacts-list">
          {topImpacts.length === 0 && (
            <p className="iv4-empty">No critical or high-severity events</p>
          )}
          {topImpacts.map((ev) => (
            <ImpactCard key={ev.id} event={ev} />
          ))}
        </div>
      </div>

      {/* Watch Officer Alerts */}
      {watchAlerts.length > 0 && (
        <div className="iv4-watch-section">
          <p className="iv4-filter-label">ACTIVE ALERTS</p>
          <div className="iv4-alerts-list">
            {watchAlerts.slice(0, 4).map((a, i) => (
              <div key={a.id || i} className="iv4-alert-row">
                <span className="iv4-alert-sev" style={{
                  color: a.severity === "critical" ? "#ff3b3b" : a.severity === "warning" ? "#f5a623" : "#00e5ff"
                }}>
                  {a.severity === "critical" ? "●" : a.severity === "warning" ? "▲" : "·"}
                </span>
                <span className="iv4-alert-msg">{a.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="iv4-watch-actions">
        <button className="iv4-action-btn">VIEW RECOMMENDED ACTIONS →</button>
      </div>
    </aside>
  );
}
