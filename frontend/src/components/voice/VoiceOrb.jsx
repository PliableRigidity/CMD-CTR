import { useEffect, useRef } from "react";

const COLORS = {
  idle:                { inner: "#3d6468", outer: "rgba(61,100,104,0.15)",  pulse: false },
  listening:           { inner: "#00e5ff", outer: "rgba(0,229,255,0.12)",   pulse: true },
  wake_detected:       { inner: "#f5a623", outer: "rgba(245,166,35,0.15)",  pulse: false },
  armed:               { inner: "#f5a623", outer: "rgba(245,166,35,0.25)",  pulse: true },
  recording:           { inner: "#ff3b3b", outer: "rgba(255,59,59,0.18)",   pulse: true },
  thinking:            { inner: "#00e5ff", outer: "rgba(0,229,255,0.15)",   pulse: false, rotate: true },
  processing:          { inner: "#00e5ff", outer: "rgba(0,229,255,0.15)",   pulse: false, rotate: true },
  speaking:            { inner: "#00ff88", outer: "rgba(0,255,136,0.15)",   pulse: true },
  executing:           { inner: "#00ff88", outer: "rgba(0,255,136,0.20)",   pulse: false },
  conversation_active: { inner: "#f5a623", outer: "rgba(245,166,35,0.18)",  pulse: true },
  listening_again:     { inner: "#00e5ff", outer: "rgba(0,229,255,0.20)",   pulse: true },
  cooldown:            { inner: "#3d6468", outer: "rgba(61,100,104,0.08)",  pulse: false },
  error:               { inner: "#ff3b3b", outer: "rgba(255,59,59,0.15)",   pulse: true },
};

const LABELS = {
  idle:                "Sleeping",
  listening:           "Wake Word",
  wake_detected:       "Wake",
  armed:               "Speak now",
  recording:           "Listening",
  thinking:            "Thinking",
  processing:          "Thinking",
  speaking:            "Speaking",
  executing:           "Executing",
  conversation_active: "Listening for reply",
  listening_again:     "Listening",
  cooldown:            "…",
  error:               "Error",
};

export default function VoiceOrb({ state = "idle", size = 48, showLabel = true, onClick }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(0);

  const cfg = COLORS[state] || COLORS.idle;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const s = size * 1.8;
    canvas.width = s * dpr;
    canvas.height = s * dpr;
    canvas.style.width = `${s}px`;
    canvas.style.height = `${s}px`;
    ctx.scale(dpr, dpr);

    let raf;
    function draw() {
      frameRef.current++;
      const f = frameRef.current;
      const cx = s / 2;
      const cy = s / 2;
      const r = size * 0.32;

      ctx.clearRect(0, 0, s, s);

      // Outer ring
      const pulseScale = cfg.pulse ? 1 + Math.sin(f * 0.04) * 0.12 : 1;
      const outerR = r * 1.6 * pulseScale;
      ctx.beginPath();
      ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
      ctx.fillStyle = cfg.outer;
      ctx.fill();

      // Second ring (armed/speaking reactive)
      if (state === "armed" || state === "speaking" || state === "recording") {
        const wave = 1 + Math.sin(f * 0.08) * 0.08;
        ctx.beginPath();
        ctx.arc(cx, cy, r * 1.3 * wave, 0, Math.PI * 2);
        ctx.strokeStyle = cfg.inner;
        ctx.globalAlpha = 0.25;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      // Rotating arc for thinking/processing
      if (cfg.rotate) {
        const angle = (f * 0.03) % (Math.PI * 2);
        ctx.beginPath();
        ctx.arc(cx, cy, r * 1.15, angle, angle + Math.PI * 1.2);
        ctx.strokeStyle = cfg.inner;
        ctx.globalAlpha = 0.5;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      // Inner orb
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      grad.addColorStop(0, cfg.inner);
      grad.addColorStop(1, cfg.outer);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      raf = requestAnimationFrame(draw);
    }
    draw();
    return () => cancelAnimationFrame(raf);
  }, [state, size, cfg]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 4,
        cursor: onClick ? "pointer" : "default",
      }}
      onClick={onClick}
      title={LABELS[state] || state}
    >
      <canvas ref={canvasRef} />
      {showLabel && (
        <span style={{
          fontSize: "0.6rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: cfg.inner,
          fontWeight: 600,
        }}>
          {LABELS[state] || state}
        </span>
      )}
    </div>
  );
}
