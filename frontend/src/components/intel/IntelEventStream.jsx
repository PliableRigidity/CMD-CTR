import { useState } from "react";

const SEV_COLOR = { critical: "#ff3b3b", high: "#f5a623", medium: "#e8d44d", low: "#00e5ff" };
const STREAM_SEVS = ["ALL EVENTS", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

function formatTime(ts) {
  if (!ts) return "--:--";
  const ms = typeof ts === "number" ? ts : parseInt(ts, 10);
  if (isNaN(ms)) return "--:--";
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function StreamRow({ item }) {
  const isQuake = item._kind === "earthquake";
  const s = isQuake
    ? ((item.mag || 0) >= 6 ? "critical" : (item.mag || 0) >= 4.5 ? "high" : (item.mag || 0) >= 3 ? "medium" : "low")
    : (item.board_priority || item.priority || "low").toLowerCase();
  const color = SEV_COLOR[s] || SEV_COLOR.low;
  const cat = isQuake ? "Seismic" : (item.category || "").replace(/_/g, " ");
  const title = isQuake ? `M${(item.mag || 0).toFixed(1)} ${item.title}` : item.title;
  const time = formatTime(item.published_at || item.time);

  return (
    <div className="iv4-stream-row">
      <span className="iv4-stream-time">{time}</span>
      <span className="iv4-stream-sev" style={{ color }}>{s.toUpperCase()}</span>
      <span className="iv4-stream-cat">{cat}</span>
      <span className="iv4-stream-title">{title}</span>
    </div>
  );
}

export default function IntelEventStream({ events = [], earthquakes = [] }) {
  const [filter, setFilter] = useState("ALL EVENTS");

  const merged = [
    ...events.map((e) => ({ ...e, _kind: "event", _ts: parseInt(e.published_at || "0", 10) || 0 })),
    ...earthquakes.map((e) => ({ ...e, _kind: "earthquake", _ts: parseInt(e.time || "0", 10) || 0 })),
  ].sort((a, b) => b._ts - a._ts);

  const filtered = filter === "ALL EVENTS" ? merged : merged.filter((item) => {
    const isQ = item._kind === "earthquake";
    const s = isQ
      ? ((item.mag || 0) >= 6 ? "critical" : (item.mag || 0) >= 4.5 ? "high" : (item.mag || 0) >= 3 ? "medium" : "low")
      : (item.board_priority || item.priority || "low").toLowerCase();
    return s === filter.toLowerCase();
  });

  return (
    <div className="iv4-stream">
      <div className="iv4-stream-head">
        <span className="iv4-section-title" style={{ fontSize: 11 }}>‹ LIVE INTEL STREAM</span>
        <div className="iv4-stream-filters">
          {STREAM_SEVS.map((s) => (
            <button
              key={s}
              className={`iv4-stream-fbtn${filter === s ? " iv4-stream-fbtn--on" : ""}`}
              onClick={() => setFilter(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <span className="iv4-stream-count">{filtered.length} EVENTS IN 24H</span>
      </div>
      <div className="iv4-stream-body">
        {filtered.slice(0, 30).map((item, i) => (
          <StreamRow key={item.id || i} item={item} />
        ))}
        {filtered.length === 0 && (
          <p className="iv4-empty" style={{ padding: "8px 12px" }}>No events match filter</p>
        )}
      </div>
    </div>
  );
}
