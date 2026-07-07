import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import IntelGlobe from "../components/intel/IntelGlobe";
import IntelLayerPanel from "../components/intel/IntelLayerPanel";
import IntelWatchPanel from "../components/intel/IntelWatchPanel";
import IntelLiveMedia from "../components/intel/IntelLiveMedia";
import IntelNewsFeed from "../components/intel/IntelNewsFeed";
import IntelEventStream from "../components/intel/IntelEventStream";
import { publicCameras } from "../data/cameras";
import { fetchWorldEvents, fetchEarthquakes, fetchWeather } from "../lib/api";

const ALL_LAYERS = ["global", "tech", "cyber", "engineering", "seismic", "weather", "supply"];

const CAT_LAYER = {
  politics: "global", conflict: "global", economics: "global",
  tech: "tech", science: "tech",
  health: "global", environment: "global", disaster: "seismic",
  culture: "global", sports: "global",
  engineering: "engineering", cyber: "cyber",
  economy: "global", general: "global",
};

function matchLayer(ev, layers) { return layers.includes(CAT_LAYER[ev.category] || "global"); }
function matchSev(ev, s) { return s === "all" || (ev.board_priority || ev.priority || "low").toLowerCase() === s; }
function matchTime(ev, w) {
  if (w === "all" || w === "live") return true;
  const ts = parseInt(ev.published_at || "0", 10);
  if (!ts) return true;
  const cut = { "1h": 3600000, "6h": 21600000, "24h": 86400000, "7d": 604800000 }[w] || Infinity;
  return Date.now() - ts < cut;
}
function qSev(m) { return m >= 6 ? "critical" : m >= 4.5 ? "high" : m >= 3 ? "medium" : "low"; }
function qMatchSev(eq, s) { return s === "all" || qSev(eq.mag || 0) === s; }
function qMatchTime(eq, w) {
  if (w === "all" || w === "live") return true;
  const ts = parseInt(eq.time || "0", 10);
  if (!ts) return true;
  const cut = { "1h": 3600000, "6h": 21600000, "24h": 86400000, "7d": 604800000 }[w] || Infinity;
  return Date.now() - ts < cut;
}

// Fetch watch officer alerts
const _host = typeof window !== "undefined" ? window.location.hostname : "localhost";
async function fetchWatchAlerts() {
  try {
    const r = await fetch(`http://${_host}:8001/api/watch`);
    if (!r.ok) return [];
    return await r.json();
  } catch { return []; }
}

export default function IntelBoardPage() {
  const [worldEvents, setWorldEvents] = useState([]);
  const [earthquakes, setEarthquakes] = useState([]);
  const [weather, setWeather] = useState([]);
  const [watchAlerts, setWatchAlerts] = useState([]);
  const [activeLayers, setActiveLayers] = useState(() => {
    try { const s = localStorage.getItem("silvia_intel_layers_v4"); return s ? JSON.parse(s) : [...ALL_LAYERS]; }
    catch { return [...ALL_LAYERS]; }
  });
  const [severity, setSeverity] = useState("all");
  const [timeWindow, setTimeWindow] = useState("24h");
  const [clock, setClock] = useState(new Date());
  const [selectedCamera, setSelectedCamera] = useState(null);

  const globeRef = useRef(null);
  const [globeDims, setGlobeDims] = useState({ width: 800, height: 600 });

  useEffect(() => { localStorage.setItem("silvia_intel_layers_v4", JSON.stringify(activeLayers)); }, [activeLayers]);

  // Resize
  useEffect(() => {
    const el = globeRef.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => {
      const { width, height } = e[0].contentRect;
      setGlobeDims({ width: Math.floor(width), height: Math.floor(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Clock
  useEffect(() => { const t = setInterval(() => setClock(new Date()), 1000); return () => clearInterval(t); }, []);

  // Data
  useEffect(() => {
    let to;
    async function load() {
      try {
        const data = await fetchWorldEvents({ live: true });
        setWorldEvents(Array.isArray(data) ? data : []);
        to = setTimeout(load, (Array.isArray(data) ? data : []).some((e) => !e.assessment) ? 20000 : 60000);
      } catch { to = setTimeout(load, 60000); }
    }
    load();
    return () => clearTimeout(to);
  }, []);

  useEffect(() => {
    const load = () => fetchEarthquakes().then(setEarthquakes).catch(() => {});
    load(); const id = setInterval(load, 300000); return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const load = () => fetchWeather().then(setWeather).catch(() => {});
    load(); const id = setInterval(load, 600000); return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const load = () => fetchWatchAlerts().then(setWatchAlerts).catch(() => {});
    load(); const id = setInterval(load, 30000); return () => clearInterval(id);
  }, []);

  const toggleLayer = useCallback((id) => {
    setActiveLayers((p) => p.includes(id) ? p.filter((l) => l !== id) : [...p, id]);
  }, []);

  // Filtered data
  const fEvents = useMemo(() =>
    worldEvents.filter((e) => matchLayer(e, activeLayers) && matchSev(e, severity) && matchTime(e, timeWindow)),
    [worldEvents, activeLayers, severity, timeWindow]);

  const fQuakes = useMemo(() =>
    activeLayers.includes("seismic")
      ? earthquakes.filter((e) => qMatchSev(e, severity) && qMatchTime(e, timeWindow))
      : [],
    [earthquakes, activeLayers, severity, timeWindow]);

  const fWeather = useMemo(() =>
    activeLayers.includes("weather") ? weather : [],
    [weather, activeLayers]);

  // Stats
  const stats = useMemo(() => {
    const s = { total: fEvents.length + fQuakes.length, critical: 0, high: 0 };
    ALL_LAYERS.forEach((l) => { s[l] = 0; });
    worldEvents.forEach((e) => {
      const layer = CAT_LAYER[e.category] || "global";
      s[layer] = (s[layer] || 0) + 1;
      const sv = (e.board_priority || e.priority || "low").toLowerCase();
      if (sv === "critical") s.critical++;
      if (sv === "high") s.high++;
    });
    s.seismic = (s.seismic || 0) + earthquakes.length;
    earthquakes.forEach((e) => { if ((e.mag || 0) >= 6) s.critical++; else if ((e.mag || 0) >= 4.5) s.high++; });
    return s;
  }, [worldEvents, earthquakes, fEvents, fQuakes]);

  const handleCameraSelect = useCallback((cam) => {
    setSelectedCamera(cam);
  }, []);

  return (
    <div className="iv4">
      {/* ═══ TOP BAR ═══ */}
      <header className="iv4-topbar">
        <div className="iv4-topbar-brand">
          <Link to="/" className="iv4-home">≡ SILVIA /</Link>
          <div className="iv4-topbar-title-block">
            <span className="iv4-topbar-sub">ENGINEERING INTELLIGENCE CENTER</span>
            <span className="iv4-topbar-main">SITUATIONAL AWARENESS</span>
          </div>
        </div>

        <div className="iv4-topbar-stats">
          <div className="iv4-stat-badge">
            <span className="iv4-stat-badge-icon">△</span>
            <span className="iv4-stat-badge-label">ALERTS</span>
            <span className="iv4-stat-badge-val" style={{ color: watchAlerts.length > 0 ? "#f5a623" : "var(--text-dim)" }}>
              {watchAlerts.length}
            </span>
          </div>
          <div className="iv4-stat-badge">
            <span className="iv4-stat-badge-icon" style={{ color: "#ff3b3b" }}>●</span>
            <span className="iv4-stat-badge-label">CRITICAL</span>
            <span className="iv4-stat-badge-val" style={{ color: "#ff3b3b" }}>{stats.critical}</span>
          </div>
          <div className="iv4-stat-badge">
            <span className="iv4-stat-badge-icon" style={{ color: "#f5a623" }}>◆</span>
            <span className="iv4-stat-badge-label">HIGH</span>
            <span className="iv4-stat-badge-val" style={{ color: "#f5a623" }}>{stats.high}</span>
          </div>
          <div className="iv4-stat-badge">
            <span className="iv4-stat-badge-icon" style={{ color: "var(--accent)" }}>◎</span>
            <span className="iv4-stat-badge-label">TOTAL</span>
            <span className="iv4-stat-badge-val">{stats.total}</span>
          </div>
        </div>

        <div className="iv4-topbar-clock">
          <span className="iv4-clock-time">{clock.toUTCString().slice(17, 25)} UTC</span>
          <span className="iv4-clock-date">{clock.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }).toUpperCase()}</span>
        </div>
      </header>

      {/* ═══ MAIN AREA ═══ */}
      <div className="iv4-main">
        {/* Left — Layers */}
        <IntelLayerPanel
          activeLayers={activeLayers}
          onToggleLayer={toggleLayer}
          severity={severity}
          onSeverityChange={setSeverity}
          timeWindow={timeWindow}
          onTimeWindowChange={setTimeWindow}
          stats={stats}
        />

        {/* Center — Globe */}
        <div className="iv4-globe-zone" ref={globeRef}>
          <div className="iv4-globe-label">
            <span>GLOBAL SITUATION MAP</span>
            <span className="iv4-globe-3d">3D</span>
          </div>
          <IntelGlobe
            events={fEvents}
            earthquakes={fQuakes}
            cameras={publicCameras}
            weather={fWeather}
            onCameraSelect={handleCameraSelect}
            width={globeDims.width}
            height={globeDims.height}
          />
          <div className="iv4-globe-bottom-label">
            <span>{fEvents.length + fQuakes.length} EVENTS · {publicCameras.length} CAMERAS · DRAG TO ROTATE · SCROLL TO ZOOM</span>
          </div>
        </div>

        {/* Right — Watch Officer */}
        <IntelWatchPanel
          events={fEvents}
          earthquakes={fQuakes}
          watchAlerts={watchAlerts}
          stats={stats}
        />
      </div>

      {/* ═══ BOTTOM ZONE ═══ */}
      <div className="iv4-bottom">
        <IntelLiveMedia cameras={publicCameras} externalFeed={selectedCamera} />
        <IntelNewsFeed events={fEvents} />
        <IntelEventStream events={fEvents} earthquakes={fQuakes} />
      </div>
    </div>
  );
}
