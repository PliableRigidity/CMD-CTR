import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  createEventsSocket,
  fetchCognitiveSnapshot,
  runCognitiveQuery,
  resetCognitive,
} from "../lib/api";

// ── Design tokens (match the other boards) ──────────────────────────────────
const T = {
  bg: "#060b14", surface: "#0d1623", border: "rgba(201,148,58,0.18)",
  borderHi: "rgba(201,148,58,0.45)", gold: "#c9943a", text: "#ddd5c5",
  textMuted: "#6b7280",
};

// Cognitive node type → base colour + radius.
const NODE_COLOR = {
  user_request: "#ffd700", query: "#f5a623", project: "#00e5ff",
  task: "#ffd166", goal: "#22d3ee", decision: "#f472b6", person: "#a3e635",
  document: "#8b5cf6", memory: "#60a5fa", agent: "#a78bfa", workflow: "#34d399",
  tool: "#fb923c", service: "#818cf8", observation: "#93c5fd",
  simulation: "#e879f9", error: "#ff4d4d",
};
const NODE_RADIUS = {
  user_request: 20, query: 12, project: 16, decision: 13, agent: 14,
  workflow: 13, tool: 11, memory: 11, simulation: 12, error: 12,
};
// State → glow intensity + ring colour (also drives brightness).
const STATE_STYLE = {
  dormant: { ring: "#334155", boost: 0.10 },
  retrieved: { ring: "#60a5fa", boost: 0.50 },
  active: { ring: "#22d3ee", boost: 0.85 },
  selected: { ring: "#facc15", boost: 1.00 },
  rejected: { ring: "#64748b", boost: 0.20 },
  running: { ring: "#34d399", boost: 0.90 },
  completed: { ring: "#10b981", boost: 0.70 },
  blocked: { ring: "#f97316", boost: 0.60 },
  error: { ring: "#ff4d4d", boost: 0.60 },
  simulated: { ring: "#e879f9", boost: 0.50 },
  proposed: { ring: "#c084fc", boost: 0.50 },
  confirmed: { ring: "#22c55e", boost: 0.80 },
};
const EDGE_COLOR = {
  retrieved_with: "#3b82f6", related_to: "#64748b", depends_on: "#ef4444",
  contains: "#60a5fa", caused: "#f59e0b", delegated_to: "#a78bfa",
  executed_by: "#fb923c", produced: "#34d399", contradicted_by: "#ff4d4d",
  derived_from: "#818cf8", simulated_from: "#e879f9",
  selected_for_context: "#facc15", planned: "#8a6422",
};
const HALF_LIFE_MS = 45000; // client-side decay to match the backend
const VIEWS = {
  session: { label: "Active Session", types: null },
  knowledge: { label: "KOSINE Knowledge", types: new Set(["memory", "project", "task", "goal", "decision", "person", "document", "observation"]) },
  agents: { label: "Agents & Workflows", types: new Set(["agent", "workflow", "tool", "decision", "user_request", "service"]) },
};

// Physics
const REPULSION = 5200, SPRING_K = 0.045, SPRING_L = 150, DAMPING = 0.82,
  GRAVITY = 0.004, MAX_VEL = 9;

function nodeColor(t) { return NODE_COLOR[t] || "#94a3b8"; }
function nodeRadius(t) { return NODE_RADIUS[t] || 10; }
function decayed(node) {
  const dt = performance.now() - (node.lastTouch || 0);
  const base = STATE_STYLE[node.state]?.boost ?? node.activation ?? 0.3;
  return base * Math.pow(0.5, dt / HALF_LIFE_MS);
}

// ── Canvas force graph ──────────────────────────────────────────────────────
function ForceGraph({ graphRef, selectedId, onSelect, visibleTypes, search, paused }) {
  const canvasRef = useRef(null);
  const viewRef = useRef({ x: 0, y: 0, scale: 1 });
  const dragRef = useRef(null);
  const rafRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const resize = () => {
      canvas.width = canvas.clientWidth * devicePixelRatio;
      canvas.height = canvas.clientHeight * devicePixelRatio;
    };
    resize();
    window.addEventListener("resize", resize);

    const step = () => {
      const g = graphRef.current;
      const nodes = g.nodes, edges = g.edges;
      const cx = canvas.width / (2 * devicePixelRatio);
      const cy = canvas.height / (2 * devicePixelRatio);

      if (!paused) {
        for (let i = 0; i < nodes.length; i++) {
          const a = nodes[i];
          for (let j = i + 1; j < nodes.length; j++) {
            const b = nodes[j];
            let dx = a.x - b.x, dy = a.y - b.y;
            let d2 = dx * dx + dy * dy || 0.01;
            const f = REPULSION / d2;
            const d = Math.sqrt(d2);
            const fx = (dx / d) * f, fy = (dy / d) * f;
            a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
          }
          a.vx += (cx - a.x) * GRAVITY; a.vy += (cy - a.y) * GRAVITY;
        }
        const byId = g.byId;
        for (const e of edges) {
          const s = byId.get(e.source), t = byId.get(e.target);
          if (!s || !t) continue;
          const dx = t.x - s.x, dy = t.y - s.y;
          const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const f = SPRING_K * (d - SPRING_L);
          const fx = (dx / d) * f, fy = (dy / d) * f;
          s.vx += fx; s.vy += fy; t.vx -= fx; t.vy -= fy;
        }
        for (const n of nodes) {
          if (dragRef.current?.node === n) continue;
          n.vx = Math.max(-MAX_VEL, Math.min(MAX_VEL, n.vx * DAMPING));
          n.vy = Math.max(-MAX_VEL, Math.min(MAX_VEL, n.vy * DAMPING));
          n.x += n.vx; n.y += n.vy;
        }
      }

      // draw
      ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const v = viewRef.current;
      ctx.translate(v.x, v.y); ctx.scale(v.scale, v.scale);
      const byId = g.byId;
      const isVisible = (n) => (!visibleTypes || visibleTypes.has(n.type));

      for (const e of edges) {
        const s = byId.get(e.source), t = byId.get(e.target);
        if (!s || !t || !isVisible(s) || !isVisible(t)) continue;
        const age = performance.now() - (e.lastTouch || 0);
        const op = Math.max(0.06, 0.7 * Math.pow(0.5, age / 8000));
        ctx.strokeStyle = (EDGE_COLOR[e.type] || "#475569");
        ctx.globalAlpha = op;
        ctx.lineWidth = age < 1200 ? 2.2 : 1;
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke();
      }
      ctx.globalAlpha = 1;
      for (const n of nodes) {
        if (!isVisible(n)) continue;
        const act = decayed(n);
        const r = nodeRadius(n.type) * (0.65 + act * 0.7);
        const hit = search && n.label?.toLowerCase().includes(search.toLowerCase());
        const st = STATE_STYLE[n.state] || STATE_STYLE.dormant;
        // glow
        ctx.globalAlpha = 0.12 + act * 0.5;
        ctx.fillStyle = nodeColor(n.type);
        ctx.beginPath(); ctx.arc(n.x, n.y, r + 8 * act, 0, Math.PI * 2); ctx.fill();
        // body
        ctx.globalAlpha = 0.55 + act * 0.45;
        ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fill();
        // state ring
        ctx.globalAlpha = 1;
        ctx.lineWidth = n.id === selectedId ? 3.5 : (hit ? 3 : 1.6);
        ctx.strokeStyle = n.id === selectedId ? "#fff" : (hit ? T.gold : st.ring);
        ctx.stroke();
        if (n.state === "simulated") { // dashed for simulations (not facts)
          ctx.setLineDash([4, 3]); ctx.strokeStyle = "#e879f9"; ctx.stroke();
          ctx.setLineDash([]);
        }
        if (act > 0.35 || n.id === selectedId) {
          ctx.globalAlpha = 0.85; ctx.fillStyle = T.text;
          ctx.font = "11px ui-sans-serif, system-ui";
          ctx.fillText((n.label || "").slice(0, 22), n.x + r + 4, n.y + 3);
        }
        ctx.globalAlpha = 1;
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => { cancelAnimationFrame(rafRef.current); window.removeEventListener("resize", resize); };
  }, [graphRef, selectedId, visibleTypes, search, paused]);

  // interaction
  const toWorld = (ev) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const v = viewRef.current;
    return { x: (ev.clientX - rect.left - v.x) / v.scale, y: (ev.clientY - rect.top - v.y) / v.scale };
  };
  const pick = (p) => {
    const g = graphRef.current;
    for (let i = g.nodes.length - 1; i >= 0; i--) {
      const n = g.nodes[i];
      if (visibleTypes && !visibleTypes.has(n.type)) continue;
      const r = nodeRadius(n.type) * 1.4 + 6;
      if ((n.x - p.x) ** 2 + (n.y - p.y) ** 2 <= r * r) return n;
    }
    return null;
  };
  const onDown = (ev) => {
    const p = toWorld(ev); const n = pick(p);
    if (n) { dragRef.current = { node: n, moved: false }; }
    else dragRef.current = { pan: true, sx: ev.clientX, sy: ev.clientY, ox: viewRef.current.x, oy: viewRef.current.y };
  };
  const onMove = (ev) => {
    const d = dragRef.current; if (!d) return;
    if (d.node) { const p = toWorld(ev); d.node.x = p.x; d.node.y = p.y; d.node.vx = d.node.vy = 0; d.moved = true; }
    else if (d.pan) { viewRef.current.x = d.ox + (ev.clientX - d.sx); viewRef.current.y = d.oy + (ev.clientY - d.sy); }
  };
  const onUp = (ev) => {
    const d = dragRef.current;
    if (d?.node && !d.moved) onSelect(d.node.id);
    else if (d?.pan && Math.abs(ev.clientX - d.sx) < 3 && Math.abs(ev.clientY - d.sy) < 3) onSelect(null);
    dragRef.current = null;
  };
  const onWheel = (ev) => {
    ev.preventDefault();
    const v = viewRef.current; const rect = canvasRef.current.getBoundingClientRect();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    const factor = ev.deltaY < 0 ? 1.1 : 0.9;
    const ns = Math.max(0.2, Math.min(3, v.scale * factor));
    v.x = mx - (mx - v.x) * (ns / v.scale); v.y = my - (my - v.y) * (ns / v.scale); v.scale = ns;
  };
  return (
    <canvas ref={canvasRef} style={{ width: "100%", height: "100%", cursor: "grab", display: "block" }}
      onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp} onWheel={onWheel} />
  );
}

// ── Graph store (mutable ref, updated by live events) ───────────────────────
function makeGraph() { return { nodes: [], edges: [], byId: new Map(), byEdge: new Map() }; }
function upsertNode(g, spec, cx, cy) {
  let n = g.byId.get(spec.id);
  if (!n) {
    n = { id: spec.id, x: cx + (Math.random() - 0.5) * 200, y: cy + (Math.random() - 0.5) * 200, vx: 0, vy: 0 };
    g.nodes.push(n); g.byId.set(spec.id, n);
  }
  n.type = spec.type || n.type || "memory";
  n.label = spec.label || n.label || spec.id;
  n.provider = spec.provider ?? n.provider ?? "";
  n.state = spec.state || n.state || "active";
  n.activation = spec.activation ?? (STATE_STYLE[n.state]?.boost ?? 0.4);
  n.meta = { ...(n.meta || {}), ...(spec.meta || {}) };
  n.lastTouch = performance.now();
}
function upsertEdge(g, spec) {
  if (!spec.source || !spec.target) return;
  const id = spec.id || `${spec.source}->${spec.type || "related"}->${spec.target}`;
  let e = g.byEdge.get(id);
  if (!e) { e = { id, source: spec.source, target: spec.target }; g.edges.push(e); g.byEdge.set(id, e); }
  e.type = spec.type || e.type || "related_to";
  e.lastTouch = performance.now();
}

export default function CognitiveGraphPage() {
  const graphRef = useRef(makeGraph());
  const [, forceRender] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [events, setEvents] = useState([]);
  const [view, setView] = useState("session");
  const [search, setSearch] = useState("");
  const [paused, setPaused] = useState(false);
  const [connected, setConnected] = useState(false);
  const [degraded, setDegraded] = useState({}); // provider -> true
  const [task, setTask] = useState("");
  const [running, setRunning] = useState(false);
  const [typeFilter, setTypeFilter] = useState(null); // null = all
  const sessionId = useRef("cog-" + Math.random().toString(36).slice(2, 8)).current;

  const centre = () => [innerWidth / 2, 300];

  const applyEvent = useCallback((evt) => {
    const g = graphRef.current; const [cx, cy] = centre();
    (evt.nodes || []).forEach((s) => upsertNode(g, s, cx, cy));
    (evt.edges || []).forEach((s) => upsertEdge(g, s));
    if (evt.event_type === "provider_degraded" && evt.provider)
      setDegraded((d) => ({ ...d, [evt.provider]: true }));
    if (evt.event_type === "provider_recovered" && evt.provider)
      setDegraded((d) => { const n = { ...d }; delete n[evt.provider]; return n; });
    setEvents((prev) => [...prev.slice(-140), evt]);
  }, [sessionId]);

  // seed from snapshot
  useEffect(() => {
    let alive = true;
    fetchCognitiveSnapshot("", 300).then((snap) => {
      if (!alive) return;
      const g = makeGraph(); const [cx, cy] = centre();
      (snap.graph?.nodes || []).forEach((s) => upsertNode(g, s, cx, cy));
      (snap.graph?.edges || []).forEach((s) => upsertEdge(g, s));
      graphRef.current = g;
      setEvents(snap.events || []);
      forceRender((x) => x + 1);
    }).catch(() => {});
    return () => { alive = false; };
  }, []);

  // live socket (shared events channel, filtered to cognitive)
  useEffect(() => {
    let ws, closed = false, retry;
    const connect = () => {
      try { ws = createEventsSocket(); } catch { return; }
      ws.onopen = () => setConnected(true);
      ws.onclose = () => { setConnected(false); if (!closed) retry = setTimeout(connect, 1500); };
      ws.onerror = () => { try { ws.close(); } catch { /* noop */ } };
      ws.onmessage = (m) => {
        let parsed; try { parsed = JSON.parse(m.data); } catch { return; }
        if (parsed?.type === "cognitive" && parsed.event) applyEvent(parsed.event);
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); try { ws && ws.close(); } catch { /* noop */ } };
  }, [applyEvent]);

  const visibleTypes = useMemo(() => {
    const viewTypes = VIEWS[view].types;
    if (!viewTypes && !typeFilter) return null;
    if (viewTypes && typeFilter) return new Set([...viewTypes].filter((t) => typeFilter.has(t)));
    return typeFilter || viewTypes;
  }, [view, typeFilter]);

  const presentTypes = useMemo(() => {
    const s = new Set(); graphRef.current.nodes.forEach((n) => s.add(n.type)); return [...s].sort();
  }, [events.length]);

  const selected = selectedId ? graphRef.current.byId.get(selectedId) : null;
  const selEdges = useMemo(() => {
    if (!selected) return { out: [], in: [] };
    const g = graphRef.current;
    return {
      out: g.edges.filter((e) => e.source === selectedId),
      in: g.edges.filter((e) => e.target === selectedId),
    };
  }, [selectedId, events.length]);

  const doRun = async () => {
    if (!task.trim()) return;
    setRunning(true);
    try { await runCognitiveQuery({ task: task.trim(), session_id: sessionId }); }
    catch { /* surfaced via events / banner */ }
    finally { setRunning(false); }
  };
  const doReset = async () => {
    try { await resetCognitive(); } catch { /* noop */ }
    graphRef.current = makeGraph(); setSelectedId(null); setEvents([]); forceRender((x) => x + 1);
  };

  const chip = (active) => ({
    padding: "4px 10px", borderRadius: 6, cursor: "pointer", fontSize: 12,
    border: `1px solid ${active ? T.borderHi : T.border}`,
    background: active ? "rgba(201,148,58,0.15)" : "transparent",
    color: active ? T.gold : T.textMuted,
  });

  return (
    <div style={{ height: "100vh", background: T.bg, color: T.text, display: "flex", flexDirection: "column", fontFamily: "ui-sans-serif, system-ui" }}>
      {/* header */}
      <div style={{ padding: "12px 18px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <Link to="/" style={{ color: T.gold, textDecoration: "none", fontWeight: 600 }}>← SILVIA</Link>
        <strong style={{ letterSpacing: 0.5 }}>Cognitive Graph</strong>
        <span style={{ fontSize: 11, color: T.textMuted }}>
          observable system activity — memory retrieval, activation, agents, tools, decisions.
          <b style={{ color: "#94a3b8" }}> Not the model’s hidden chain-of-thought.</b>
        </span>
        <span style={{ marginLeft: "auto", fontSize: 12, color: connected ? "#34d399" : "#f97316" }}>
          {connected ? "● live" : "○ reconnecting"}
        </span>
      </div>

      {/* degradation banner */}
      {Object.keys(degraded).length > 0 && (
        <div style={{ padding: "6px 18px", background: "rgba(249,115,22,0.15)", color: "#fdba74", fontSize: 12, borderBottom: `1px solid ${T.border}` }}>
          ⚠ Provider degraded: {Object.keys(degraded).join(", ")} — showing available providers only; no fabricated results.
        </div>
      )}

      {/* controls */}
      <div style={{ padding: "8px 18px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", borderBottom: `1px solid ${T.border}` }}>
        {Object.entries(VIEWS).map(([k, v]) => (
          <div key={k} style={chip(view === k)} onClick={() => setView(k)}>{v.label}</div>
        ))}
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="search nodes…"
          style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.text, padding: "5px 8px", borderRadius: 6, fontSize: 12, width: 140 }} />
        <div style={chip(paused)} onClick={() => setPaused((p) => !p)}>{paused ? "▶ resume" : "⏸ pause"}</div>
        <div style={chip(false)} onClick={doReset} title="Clear transient visual state (does not delete memory)">↺ clear view</div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <input value={task} onChange={(e) => setTask(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doRun()}
            placeholder="run a cognition query… e.g. status of Silvia"
            style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.text, padding: "5px 10px", borderRadius: 6, fontSize: 12, width: 260 }} />
          <button onClick={doRun} disabled={running}
            style={{ background: T.gold, color: "#0b0b0b", border: "none", borderRadius: 6, padding: "5px 12px", fontWeight: 600, cursor: "pointer", opacity: running ? 0.6 : 1 }}>
            {running ? "running…" : "Run"}
          </button>
        </div>
      </div>

      {/* type filters */}
      <div style={{ padding: "6px 18px", display: "flex", gap: 6, flexWrap: "wrap", borderBottom: `1px solid ${T.border}` }}>
        <div style={chip(!typeFilter)} onClick={() => setTypeFilter(null)}>all types</div>
        {presentTypes.map((t) => {
          const active = typeFilter?.has(t);
          return (
            <div key={t} style={{ ...chip(active), color: active ? nodeColor(t) : T.textMuted, borderColor: active ? nodeColor(t) : T.border }}
              onClick={() => setTypeFilter((prev) => {
                const next = new Set(prev || presentTypes);
                if (!prev) { next.clear(); next.add(t); }
                else if (next.has(t)) next.delete(t); else next.add(t);
                return next.size ? next : null;
              })}>
              <span style={{ color: nodeColor(t) }}>●</span> {t}
            </div>
          );
        })}
      </div>

      {/* body: graph + inspector */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ flex: 1, position: "relative", minWidth: 0 }}>
          <ForceGraph graphRef={graphRef} selectedId={selectedId} onSelect={setSelectedId}
            visibleTypes={visibleTypes} search={search} paused={paused} />
          <div style={{ position: "absolute", bottom: 10, left: 12, fontSize: 11, color: T.textMuted }}>
            {graphRef.current.nodes.length} nodes · {graphRef.current.edges.length} edges · session {sessionId}
          </div>
        </div>

        {/* inspector */}
        <div style={{ width: 320, borderLeft: `1px solid ${T.border}`, background: T.surface, overflowY: "auto", padding: 14, fontSize: 13 }}>
          {selected ? (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: nodeColor(selected.type), fontSize: 18 }}>●</span>
                <strong>{selected.label}</strong>
              </div>
              <Row k="type" v={selected.type} />
              <Row k="provider" v={selected.provider || "—"} />
              <Row k="state" v={selected.state} vc={STATE_STYLE[selected.state]?.ring} />
              <Row k="activation" v={decayed(selected).toFixed(2)} />
              <Row k="in model context" v={selected.state === "selected" ? "yes" : (selected.state === "rejected" ? "no (rejected)" : "—")} />
              <Row k="nature" v={selected.state === "simulated" ? "SIMULATED (not fact)" : selected.state === "proposed" ? "PROPOSED (needs review)" : selected.state === "confirmed" ? "confirmed" : "observed"} />
              {selected.meta?.reason && <Row k="why" v={String(selected.meta.reason)} />}
              {selected.meta?.source && <Row k="source" v={String(selected.meta.source)} />}
              {selected.meta?.rerank && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ color: T.textMuted, fontSize: 11, marginBottom: 3 }}>rerank breakdown</div>
                  {Object.entries(selected.meta.rerank).map(([k, val]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                      <span style={{ color: T.textMuted }}>{k}</span><span>{typeof val === "number" ? val.toFixed(3) : String(val)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div style={{ marginTop: 10, color: T.textMuted, fontSize: 11 }}>relationships</div>
              {[...selEdges.out.map((e) => ["→", e.type, e.target]), ...selEdges.in.map((e) => ["←", e.type, e.source])]
                .slice(0, 30).map(([d, ty, other], i) => (
                  <div key={i} style={{ fontSize: 11, cursor: "pointer" }} onClick={() => setSelectedId(other)}>
                    {d} <span style={{ color: EDGE_COLOR[ty] || "#94a3b8" }}>{ty}</span> {graphRef.current.byId.get(other)?.label || other}
                  </div>
                ))}
              <div style={{ marginTop: 8, fontSize: 10, color: T.textMuted, wordBreak: "break-all" }}>id: {selected.id}</div>
            </div>
          ) : (
            <div style={{ color: T.textMuted }}>
              <p>Click a node to inspect its provenance, activation, why it was retrieved/selected, and its relationships.</p>
              <p style={{ marginTop: 10 }}>Recent activity:</p>
              {events.slice(-14).reverse().map((e, i) => (
                <div key={i} style={{ fontSize: 11, borderLeft: `2px solid ${nodeColor(e.node_ids?.length ? "memory" : "query")}`, paddingLeft: 6, marginBottom: 4 }}>
                  <span style={{ color: T.gold }}>{e.event_type}</span>
                  <div style={{ color: T.textMuted }}>{e.explanation}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v, vc }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, fontSize: 12 }}>
      <span style={{ color: "#6b7280" }}>{k}</span>
      <span style={{ color: vc || "#ddd5c5", textAlign: "right", maxWidth: 200, wordBreak: "break-word" }}>{v}</span>
    </div>
  );
}
