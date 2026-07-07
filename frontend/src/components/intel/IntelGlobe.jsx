import { useRef, useEffect, useCallback, useMemo } from "react";
import Globe from "react-globe.gl";

const SEV_COLOR = {
  critical: "#ff3b3b",
  high:     "#f5a623",
  medium:   "#e8d44d",
  low:      "#00e5ff",
};

const RING_CFG = {
  critical: { maxR: 5.5, spd: 1.2, rep: 700  },
  high:     { maxR: 4,   spd: 1.5, rep: 1000 },
  medium:   { maxR: 2.8, spd: 2.0, rep: 1500 },
};

function sev(ev) {
  const p = (ev.board_priority || ev.priority || "low").toLowerCase();
  return SEV_COLOR[p] ? p : "low";
}

function quakeSev(mag) {
  if (mag >= 6) return "critical";
  if (mag >= 4.5) return "high";
  if (mag >= 3) return "medium";
  return "low";
}

function tip(html) {
  return `<div style="background:rgba(3,8,11,0.92);border:1px solid rgba(18,200,216,0.30);padding:5px 10px;border-radius:3px;color:#d7fff7;font-family:'IBM Plex Mono',monospace;font-size:10px;font-weight:500;white-space:nowrap;backdrop-filter:blur(8px);box-shadow:0 2px 12px rgba(0,0,0,.7);">${html}</div>`;
}

export default function IntelGlobe({
  events = [],
  earthquakes = [],
  cameras = [],
  weather = [],
  onSelect,
  onCameraSelect,
  width,
  height,
}) {
  const gRef = useRef();

  useEffect(() => {
    if (!gRef.current) return;
    const c = gRef.current.controls();
    c.autoRotate = true;
    c.autoRotateSpeed = 0.35;
    c.enableDamping = true;
    c.dampingFactor = 0.05;
    c.rotateSpeed = 0.5;
    c.zoomSpeed = 0.7;
    c.minDistance = 115;
    c.maxDistance = 380;
    gRef.current.pointOfView({ lat: 20, lng: 15, altitude: 2.3 }, 0);
  }, []);

  const handleClick = useCallback((pt) => {
    if (pt._cam && onCameraSelect) { onCameraSelect(pt._data); return; }
    if (onSelect && pt._id) onSelect(pt._id, pt._kind);
  }, [onSelect, onCameraSelect]);

  const points = useMemo(() => {
    const pts = [];

    events.forEach((ev) => {
      const lat = ev.lat ?? ev.latitude;
      const lng = ev.lng ?? ev.longitude;
      if (lat == null || lng == null) return;
      const s = sev(ev);
      pts.push({
        lat, lng,
        size: s === "critical" ? 0.38 : s === "high" ? 0.30 : s === "medium" ? 0.22 : 0.16,
        color: SEV_COLOR[s],
        alt: 0.012,
        _id: ev.id, _kind: "event", _cam: false, _data: ev,
        _label: `<span style="color:${SEV_COLOR[s]}">●</span> ${ev.title || ev.category}`,
      });
    });

    earthquakes.forEach((eq) => {
      const s = quakeSev(eq.mag || 0);
      pts.push({
        lat: eq.lat, lng: eq.lng,
        size: Math.max(0.14, (eq.mag || 2) / 14),
        color: SEV_COLOR[s],
        alt: 0.004,
        _id: eq.id, _kind: "earthquake", _cam: false, _data: eq,
        _label: `<span style="color:${SEV_COLOR[s]}">◆</span> M${(eq.mag || 0).toFixed(1)} — ${eq.title || "Seismic"}`,
      });
    });

    cameras.forEach((cam) => {
      pts.push({
        lat: cam.lat, lng: cam.lng,
        size: 0.12,
        color: "#00e5ff55",
        alt: 0.002,
        _id: cam.id, _kind: "camera", _cam: true, _data: cam,
        _label: `<span style="color:#00e5ff">📹</span> ${cam.name}`,
      });
    });

    weather.forEach((w) => {
      pts.push({
        lat: w.lat, lng: w.lng,
        size: 0.10,
        color: "#4ade8044",
        alt: 0.001,
        _id: w.id, _kind: "weather", _cam: false, _data: w,
        _label: `${w.name}: ${w.temp?.toFixed(0)}°C ${w.condition}`,
      });
    });

    return pts;
  }, [events, earthquakes, cameras, weather]);

  const rings = useMemo(() => {
    const r = [];

    events.forEach((ev) => {
      const lat = ev.lat ?? ev.latitude;
      const lng = ev.lng ?? ev.longitude;
      if (lat == null || lng == null) return;
      const s = sev(ev);
      const cfg = RING_CFG[s];
      if (!cfg) return;
      r.push({ lat, lng, maxR: cfg.maxR, propagationSpeed: cfg.spd, repeatPeriod: cfg.rep, color: SEV_COLOR[s] });
    });

    earthquakes.forEach((eq) => {
      const s = quakeSev(eq.mag || 0);
      const cfg = RING_CFG[s];
      if (!cfg) return;
      r.push({ lat: eq.lat, lng: eq.lng, maxR: (eq.mag || 2) * 0.6, propagationSpeed: cfg.spd, repeatPeriod: cfg.rep, color: SEV_COLOR[s] });
    });

    return r;
  }, [events, earthquakes]);

  return (
    <div style={{ width: "100%", height: "100%", background: "#020408", position: "relative" }}>
      {/* Atmosphere glow effect */}
      <div style={{
        position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1,
        background: "radial-gradient(ellipse at center, rgba(18,200,216,0.04) 0%, rgba(18,200,216,0.015) 30%, transparent 65%)",
      }} />
      <Globe
        ref={gRef}
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        backgroundColor="rgba(0,0,0,0)"
        width={width}
        height={height}
        showAtmosphere={true}
        atmosphereColor="#1890a0"
        atmosphereAltitude={0.22}
        pointsData={points}
        pointAltitude="alt"
        pointColor="color"
        pointRadius="size"
        onPointClick={handleClick}
        pointLabel={(d) => tip(d._label)}
        ringsData={rings}
        ringColor="color"
        ringMaxRadius="maxR"
        ringPropagationSpeed="propagationSpeed"
        ringRepeatPeriod="repeatPeriod"
      />
    </div>
  );
}
