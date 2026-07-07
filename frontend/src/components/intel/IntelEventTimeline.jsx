const SEVERITY_COLORS = {
  critical: "#ff3b3b",
  high:     "#f5a623",
  medium:   "#e8d44d",
  low:      "#00e5ff",
};

function formatTime(ts) {
  if (!ts) return "--:--";
  const ms = typeof ts === "number" ? ts : parseInt(ts, 10);
  if (isNaN(ms)) return "--:--";
  const d = new Date(ms);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function TimelineItem({ item, selected, onClick }) {
  const isQuake = item._kind === "earthquake";
  const sev = isQuake
    ? ((item.mag || 0) >= 6 ? "critical" : (item.mag || 0) >= 4.5 ? "high" : (item.mag || 0) >= 3 ? "medium" : "low")
    : (item.board_priority || item.priority || "low").toLowerCase();
  const sevColor = SEVERITY_COLORS[sev] || SEVERITY_COLORS.low;
  const cat = isQuake ? "SEISMIC" : (item.category || "").toUpperCase().slice(0, 8);
  const time = formatTime(item.published_at || item.time);
  const title = isQuake ? `M${(item.mag || 0).toFixed(1)} ${item.title}` : item.title;

  return (
    <button
      className={`intel-tl-item${selected ? " intel-tl-item--selected" : ""}`}
      onClick={() => onClick(item.id, item._kind)}
    >
      <span className="intel-tl-time">{time}</span>
      <span className="intel-tl-dot" style={{ background: sevColor }} />
      <span className="intel-tl-cat">{cat}</span>
      <span className="intel-tl-title">{title}</span>
    </button>
  );
}

export default function IntelEventTimeline({
  events = [],
  earthquakes = [],
  selectedId,
  onSelect,
}) {
  // Merge and sort by timestamp, newest first
  const merged = [
    ...events.map((e) => ({
      ...e,
      _kind: "event",
      _ts: parseInt(e.published_at || "0", 10) || 0,
    })),
    ...earthquakes.map((e) => ({
      ...e,
      _kind: "earthquake",
      _ts: parseInt(e.time || "0", 10) || 0,
    })),
  ].sort((a, b) => b._ts - a._ts);

  return (
    <div className="intel-timeline">
      <div className="intel-timeline-header">
        <span className="intel-panel-eyebrow">LIVE INTEL STREAM</span>
        <span className="intel-timeline-count">{merged.length} events</span>
      </div>
      <div className="intel-timeline-scroll">
        {merged.map((item) => (
          <TimelineItem
            key={item.id}
            item={item}
            selected={selectedId === item.id}
            onClick={onSelect}
          />
        ))}
        {merged.length === 0 && (
          <span className="intel-empty" style={{ padding: "8px 12px" }}>Awaiting intel feeds...</span>
        )}
      </div>
    </div>
  );
}
