import { useEffect, useRef, useState } from "react";
import { fetchNodeTelemetryHistory } from "../../lib/api";

const LINES = [
  { key: "cpu",   color: "#00e5ff", label: "CPU" },
  { key: "ram",   color: "#d4af37", label: "RAM" },
  { key: "disk",  color: "#f97316", label: "Disk" },
];
const ROBOTICS_LINES = [
  { key: "battery_pct", color: "#22c55e", label: "Bat" },
  { key: "altitude",    color: "#a78bfa", label: "Alt" },
];

const CHART_H = 52;
const PADDING = { top: 4, bottom: 12, left: 0, right: 0 };

export default function TelemetryChart({ nodeId, isRobotics = false, livePoint = null }) {
  const canvasRef = useRef(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchNodeTelemetryHistory(nodeId, 6)
      .then((data) => { if (!cancelled) { setHistory(data); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [nodeId]);

  // Append live WebSocket point to history buffer (max 200 points)
  const fullData = useRef([]);
  useEffect(() => {
    fullData.current = history.slice(-200);
  }, [history]);

  useEffect(() => {
    if (!livePoint) return;
    fullData.current = [...fullData.current.slice(-199), livePoint];
    draw();
  }, [livePoint]);

  const activeLinesConfig = isRobotics ? ROBOTICS_LINES : LINES;

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const data = fullData.current;
    const c = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    const plotH = H - PADDING.top - PADDING.bottom;

    c.clearRect(0, 0, W, H);

    // Background grid line at 50%
    c.strokeStyle = "rgba(255,255,255,0.06)";
    c.lineWidth = 1;
    c.beginPath();
    const midY = PADDING.top + plotH * 0.5;
    c.moveTo(0, midY);
    c.lineTo(W, midY);
    c.stroke();

    if (data.length < 2) {
      c.fillStyle = "rgba(255,255,255,0.2)";
      c.font = "10px JetBrains Mono, monospace";
      c.textAlign = "center";
      c.fillText("Collecting data…", W / 2, H / 2 + 4);
      return;
    }

    const n = data.length;
    const xStep = W / (n - 1);

    activeLinesConfig.forEach(({ key, color }) => {
      const vals = data.map((d) => d[key]);
      if (vals.every((v) => v == null)) return;

      c.beginPath();
      c.strokeStyle = color;
      c.lineWidth = 1.5;
      c.lineJoin = "round";

      let started = false;
      vals.forEach((v, i) => {
        if (v == null) return;
        const x = i * xStep;
        const pct = Math.min(100, Math.max(0, v)) / 100;
        const y = PADDING.top + plotH * (1 - pct);
        if (!started) { c.moveTo(x, y); started = true; }
        else c.lineTo(x, y);
      });
      c.stroke();
    });

    // X-axis time labels (first and last)
    if (data[0]?.timestamp && data[n - 1]?.timestamp) {
      c.fillStyle = "rgba(255,255,255,0.35)";
      c.font = "9px JetBrains Mono, monospace";
      c.textAlign = "left";
      c.fillText(_fmtTime(data[0].timestamp), 2, H - 2);
      c.textAlign = "right";
      c.fillText(_fmtTime(data[n - 1].timestamp), W - 2, H - 2);
    }
  }

  useEffect(() => {
    if (!loading) draw();
  }, [history, loading]);

  // Legend
  const legend = activeLinesConfig.map(({ key, color, label }) => {
    const last = [...fullData.current].reverse().find((d) => d[key] != null);
    const val = last ? `${last[key].toFixed(0)}${key === "altitude" ? "m" : "%"}` : "—";
    return { color, label, val };
  });

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", gap: 10, marginBottom: 4, flexWrap: "wrap" }}>
        {legend.map(({ color, label, val }) => (
          <span key={label} style={{ fontSize: 10, color, fontFamily: "JetBrains Mono, monospace" }}>
            {label} {val}
          </span>
        ))}
      </div>
      <canvas
        ref={canvasRef}
        width={320}
        height={CHART_H}
        style={{ width: "100%", height: CHART_H, display: "block", borderRadius: 3 }}
      />
    </div>
  );
}

function _fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}
