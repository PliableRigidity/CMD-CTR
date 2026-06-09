import { useEffect, useRef } from "react";

export default function WaveformVisualizer({ stream, active }) {
  const canvasRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    if (!active || !stream) return;

    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    const canvas = canvasRef.current;
    const draw = () => {
      if (!canvas) return;
      const c = canvas.getContext("2d");
      const buf = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(buf);

      c.clearRect(0, 0, canvas.width, canvas.height);
      const barW = canvas.width / buf.length;
      buf.forEach((val, i) => {
        const h = (val / 255) * canvas.height;
        const alpha = 0.4 + (val / 255) * 0.6;
        c.fillStyle = `rgba(212, 175, 55, ${alpha})`;
        c.fillRect(i * barW, canvas.height - h, barW - 1, h);
      });

      rafRef.current = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(rafRef.current);
      ctx.close();
    };
  }, [active, stream]);

  return (
    <canvas
      ref={canvasRef}
      width={220}
      height={40}
      style={{ display: active ? "block" : "none", borderRadius: 4 }}
    />
  );
}
