import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fetchKnowledgeGraph, fetchProjectGraph, rebuildKnowledgeGraph } from "../lib/api";

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  bg:        "#060b14",
  surface:   "#0d1623",
  border:    "rgba(201,148,58,0.18)",
  borderHi:  "rgba(201,148,58,0.45)",
  gold:      "#c9943a",
  goldDim:   "#8a6422",
  text:      "#ddd5c5",
  textMuted: "#6b7280",
};

// ── Node type → colour mapping ────────────────────────────────────────────────
const NODE_COLOR = {
  project:    "#00e5ff",
  component:  "#f5a623",
  node:       "#00ff88",
  service:    "#a78bfa",
  order:      "#ff3b3b",
  task:       "#ffd700",
  document:   "#8b5cf6",
  capability: "#60a5fa",
  roadmap:    "#f472b6",
};

const NODE_RADIUS = {
  project:    18,
  component:  13,
  node:       15,
  service:    11,
  order:      10,
  task:       9,
  document:   12,
  capability: 10,
  roadmap:    10,
};

const EDGE_COLOR = {
  uses:        "#f5a623",
  requires:    "#ff3b3b",
  depends_on:  "#ef4444",
  blocked_by:  "#dc2626",
  hosted_on:   "#00ff88",
  related_to:  "#6b728055",
  ordered_by:  "#f97316",
  supports:    "#22c55e",
  tracks:      "#a78bfa",
  contains:    "#60a5fa",
  implements:  "#818cf8",
  assigned_to: "#c084fc",
};

const ALL_TYPES = ["project", "component", "node", "service", "order", "task", "document", "capability", "roadmap"];

// ── Force simulation constants ────────────────────────────────────────────────
const REPULSION   = 4000;
const SPRING_K    = 0.04;
const SPRING_L    = 140;
const DAMPING     = 0.82;
const GRAVITY     = 0.003;
const MAX_VEL     = 8;

// ── ForceGraph canvas component ───────────────────────────────────────────────

function ForceGraph({ nodes, edges, selectedId, onSelect, filterTypes, searchQuery }) {
  const canvasRef  = useRef(null);
  const stateRef   = useRef({ nodes: [], edges: [], animId: null, scale: 1, panX: 0, panY: 0,
                               dragging: null, panning: false, lastMouse: null, hoverId: null });
  const S = stateRef.current;

  // Build simulation state from props
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const W = canvas.width, H = canvas.height;

    // Initialise node positions in a radial layout
    const existing = new Map(S.nodes.map(n => [n.id, n]));
    S.nodes = nodes.map((n, i) => {
      const prev = existing.get(n.id);
      if (prev) return { ...prev, label: n.label, type: n.type };
      const angle = (i / nodes.length) * Math.PI * 2;
      const r = Math.min(W, H) * 0.3;
      return {
        id:   n.id,
        label: n.label,
        type: n.type,
        x:    W / 2 + Math.cos(angle) * r + (Math.random() - 0.5) * 60,
        y:    H / 2 + Math.sin(angle) * r + (Math.random() - 0.5) * 60,
        vx:   0, vy: 0,
      };
    });
    S.edges = edges;
  }, [nodes, edges]); // eslint-disable-line react-hooks/exhaustive-deps

  // Animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    function tick() {
      const simNodes = S.nodes;
      const simEdges = S.edges;
      const W = canvas.width, H = canvas.height;

      // Filtered set for display
      const visibleIds = new Set(
        simNodes
          .filter(n => {
            if (filterTypes.size > 0 && !filterTypes.has(n.type)) return false;
            if (searchQuery) return n.label.toLowerCase().includes(searchQuery.toLowerCase());
            return true;
          })
          .map(n => n.id)
      );

      // Physics on ALL nodes (even hidden ones stay in place)
      for (let i = 0; i < simNodes.length; i++) {
        const a = simNodes[i];
        let fx = 0, fy = 0;

        // Repulsion between all pairs
        for (let j = 0; j < simNodes.length; j++) {
          if (i === j) continue;
          const b = simNodes[j];
          const dx = a.x - b.x || 0.01;
          const dy = a.y - b.y || 0.01;
          const d2 = dx * dx + dy * dy;
          const f  = REPULSION / Math.max(d2, 1);
          fx += dx * f / Math.sqrt(Math.max(d2, 1));
          fy += dy * f / Math.sqrt(Math.max(d2, 1));
        }

        // Spring attraction along edges
        for (const e of simEdges) {
          let other = null;
          if (e.source === a.id) other = simNodes.find(n => n.id === e.target);
          if (e.target === a.id) other = simNodes.find(n => n.id === e.source);
          if (!other) continue;
          const dx = other.x - a.x;
          const dy = other.y - a.y;
          const d  = Math.sqrt(dx * dx + dy * dy) || 1;
          const f  = SPRING_K * (d - SPRING_L);
          fx += dx / d * f;
          fy += dy / d * f;
        }

        // Gravity toward centre
        fx += (W / 2 - a.x) * GRAVITY;
        fy += (H / 2 - a.y) * GRAVITY;

        // Update velocity + position (skip dragged node)
        if (S.dragging !== a.id) {
          a.vx = (a.vx + fx) * DAMPING;
          a.vy = (a.vy + fy) * DAMPING;
          a.vx = Math.max(-MAX_VEL, Math.min(MAX_VEL, a.vx));
          a.vy = Math.max(-MAX_VEL, Math.min(MAX_VEL, a.vy));
          a.x += a.vx;
          a.y += a.vy;
        }
      }

      // ── Render ──────────────────────────────────────────────────────────────
      ctx.clearRect(0, 0, W, H);

      ctx.save();
      ctx.translate(S.panX, S.panY);
      ctx.scale(S.scale, S.scale);

      // Subtle grid
      ctx.strokeStyle = "rgba(201,148,58,0.04)";
      ctx.lineWidth = 1 / S.scale;
      for (let gx = -W; gx < W * 2; gx += 60) {
        ctx.beginPath(); ctx.moveTo(gx, -H); ctx.lineTo(gx, H * 2); ctx.stroke();
      }
      for (let gy = -H; gy < H * 2; gy += 60) {
        ctx.beginPath(); ctx.moveTo(-W, gy); ctx.lineTo(W * 2, gy); ctx.stroke();
      }

      // Edges
      for (const e of simEdges) {
        const src = simNodes.find(n => n.id === e.source);
        const tgt = simNodes.find(n => n.id === e.target);
        if (!src || !tgt) continue;
        if (!visibleIds.has(src.id) || !visibleIds.has(tgt.id)) continue;

        const alpha = (selectedId && src.id !== selectedId && tgt.id !== selectedId) ? "40" : "bb";
        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.lineTo(tgt.x, tgt.y);
        ctx.strokeStyle = (EDGE_COLOR[e.type] || "#ffffff") + alpha;
        ctx.lineWidth = selectedId && (src.id === selectedId || tgt.id === selectedId) ? 2 / S.scale : 1 / S.scale;
        ctx.stroke();

        // Arrowhead
        const dx = tgt.x - src.x, dy = tgt.y - src.y;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        const r = (NODE_RADIUS[tgt.type] || 12) + 3;
        const ax = tgt.x - dx / len * r;
        const ay = tgt.y - dy / len * r;
        const nx = -dy / len * 5, ny = dx / len * 5;
        ctx.beginPath();
        ctx.moveTo(ax + nx, ay + ny);
        ctx.lineTo(tgt.x - dx / len * r, tgt.y - dy / len * r);
        ctx.lineTo(ax - nx, ay - ny);
        ctx.fillStyle = (EDGE_COLOR[e.type] || "#ffffff") + alpha;
        ctx.fill();
      }

      // Nodes
      for (const n of simNodes) {
        if (!visibleIds.has(n.id)) continue;
        const color  = NODE_COLOR[n.type] || "#888";
        const radius = NODE_RADIUS[n.type] || 12;
        const isSelected = n.id === selectedId;
        const isHover    = n.id === S.hoverId;
        const dimmed  = selectedId && !isSelected;

        // Glow for selected
        if (isSelected) {
          ctx.shadowColor = color;
          ctx.shadowBlur  = 16;
        }

        // Outer ring for selected/hover
        if (isSelected || isHover) {
          ctx.beginPath();
          ctx.arc(n.x, n.y, radius + 4, 0, Math.PI * 2);
          ctx.strokeStyle = color + (isSelected ? "cc" : "66");
          ctx.lineWidth = 1.5 / S.scale;
          ctx.stroke();
        }
        ctx.shadowBlur = 0;

        // Fill
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color + (dimmed ? "44" : "ee");
        ctx.fill();
        ctx.strokeStyle = color + (dimmed ? "22" : "88");
        ctx.lineWidth = 1 / S.scale;
        ctx.stroke();

        // Label (show always for projects/nodes, only on hover/select for others)
        const showLabel = isSelected || isHover || n.type === "project" || n.type === "node";
        if (showLabel) {
          const fontSize = Math.max(9, 11 / S.scale);
          ctx.font = `${fontSize}px "JetBrains Mono", monospace`;
          ctx.fillStyle = dimmed ? T.textMuted + "88" : T.text;
          ctx.textAlign = "center";
          ctx.fillText(n.label.length > 20 ? n.label.slice(0, 18) + "…" : n.label, n.x, n.y + radius + fontSize + 2);
        }
      }

      ctx.restore();
      S.animId = requestAnimationFrame(tick);
    }

    S.animId = requestAnimationFrame(tick);
    return () => { if (S.animId) cancelAnimationFrame(S.animId); };
  }, [nodes, edges, selectedId, filterTypes, searchQuery]); // eslint-disable-line react-hooks/exhaustive-deps

  // Resize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    function resize() {
      canvas.width  = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, []);

  // Mouse → canvas coords
  function toWorld(cx, cy) {
    const canvas = canvasRef.current;
    const rect   = canvas.getBoundingClientRect();
    const mx = cx - rect.left, my = cy - rect.top;
    return [(mx - S.panX) / S.scale, (my - S.panY) / S.scale];
  }

  function hitNode(wx, wy) {
    return S.nodes.find(n => {
      const r = (NODE_RADIUS[n.type] || 12) + 4;
      return (n.x - wx) ** 2 + (n.y - wy) ** 2 <= r * r;
    });
  }

  function onMouseDown(e) {
    const [wx, wy] = toWorld(e.clientX, e.clientY);
    const hit = hitNode(wx, wy);
    if (hit) {
      S.dragging = hit.id;
    } else {
      S.panning  = true;
      S.lastMouse = [e.clientX, e.clientY];
    }
  }

  function onMouseMove(e) {
    if (S.dragging) {
      const [wx, wy] = toWorld(e.clientX, e.clientY);
      const n = S.nodes.find(n => n.id === S.dragging);
      if (n) { n.x = wx; n.y = wy; n.vx = 0; n.vy = 0; }
    } else if (S.panning && S.lastMouse) {
      const dx = e.clientX - S.lastMouse[0];
      const dy = e.clientY - S.lastMouse[1];
      S.panX += dx; S.panY += dy;
      S.lastMouse = [e.clientX, e.clientY];
    } else {
      const [wx, wy] = toWorld(e.clientX, e.clientY);
      const hit = hitNode(wx, wy);
      S.hoverId = hit ? hit.id : null;
      canvasRef.current.style.cursor = hit ? "pointer" : "grab";
    }
  }

  function onMouseUp(e) {
    if (S.dragging) {
      // click vs drag: if mouse didn't move much, treat as select
      const [wx, wy] = toWorld(e.clientX, e.clientY);
      const n = S.nodes.find(n => n.id === S.dragging);
      if (n && Math.abs(n.x - wx) < 5 && Math.abs(n.y - wy) < 5) {
        onSelect(n);
      }
      S.dragging = null;
    }
    S.panning = false; S.lastMouse = null;
  }

  function onWheel(e) {
    e.preventDefault();
    const canvas = canvasRef.current;
    const rect   = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    S.panX = mx - (mx - S.panX) * delta;
    S.panY = my - (my - S.panY) * delta;
    S.scale = Math.max(0.1, Math.min(5, S.scale * delta));
  }

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: "100%", display: "block", background: T.bg, cursor: "grab" }}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onWheel={onWheel}
    />
  );
}

// ── NodeDetail sidebar ────────────────────────────────────────────────────────

function NodeDetail({ node, edges, allNodes, onClose, onFocus }) {
  if (!node) return null;
  const color  = NODE_COLOR[node.type] || "#888";
  const outgoing = edges.filter(e => e.source === node.id).map(e => ({
    ...e, other: allNodes.find(n => n.id === e.target),
  })).filter(e => e.other);
  const incoming = edges.filter(e => e.target === node.id).map(e => ({
    ...e, other: allNodes.find(n => n.id === e.source),
  })).filter(e => e.other);

  return (
    <div style={{
      width: 260, flexShrink: 0, background: T.surface,
      borderLeft: `1px solid ${T.border}`, display: "flex",
      flexDirection: "column", overflow: "hidden",
    }}>
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 10, height: 10, borderRadius: "50%", background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 11, color: T.text, flex: 1, fontFamily: "JetBrains Mono, monospace",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {node.label}
        </span>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: T.textMuted,
          fontSize: 16, cursor: "pointer", lineHeight: 1, padding: "0 2px",
        }}>×</button>
      </div>

      <div style={{ padding: "8px 14px", borderBottom: `1px solid ${T.border}` }}>
        <span style={{
          fontSize: 9, color, border: `1px solid ${color}44`,
          borderRadius: 3, padding: "1px 6px",
          fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", letterSpacing: "0.08em",
        }}>
          {node.type}
        </span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {outgoing.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <p style={{ margin: "0 14px 6px", fontSize: 9, color: T.textMuted,
              fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              Outgoing ({outgoing.length})
            </p>
            {outgoing.map((e, i) => (
              <button key={i} onClick={() => onFocus(e.other)} style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "4px 14px", width: "100%", background: "none",
                border: "none", cursor: "pointer", textAlign: "left",
              }}
                onMouseEnter={ev => ev.currentTarget.style.background = "rgba(201,148,58,0.06)"}
                onMouseLeave={ev => ev.currentTarget.style.background = "none"}
              >
                <span style={{ width: 7, height: 7, borderRadius: "50%",
                  background: NODE_COLOR[e.other.type] || "#888", flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 10, color: T.text,
                  fontFamily: "JetBrains Mono, monospace", overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {e.other.label}
                </span>
                <span style={{ fontSize: 8, color: EDGE_COLOR[e.type] || T.textMuted,
                  fontFamily: "JetBrains Mono, monospace", flexShrink: 0 }}>
                  {e.type}
                </span>
              </button>
            ))}
          </div>
        )}
        {incoming.length > 0 && (
          <div>
            <p style={{ margin: "0 14px 6px", fontSize: 9, color: T.textMuted,
              fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              Incoming ({incoming.length})
            </p>
            {incoming.map((e, i) => (
              <button key={i} onClick={() => onFocus(e.other)} style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "4px 14px", width: "100%", background: "none",
                border: "none", cursor: "pointer", textAlign: "left",
              }}
                onMouseEnter={ev => ev.currentTarget.style.background = "rgba(201,148,58,0.06)"}
                onMouseLeave={ev => ev.currentTarget.style.background = "none"}
              >
                <span style={{ width: 7, height: 7, borderRadius: "50%",
                  background: NODE_COLOR[e.other.type] || "#888", flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 10, color: T.text,
                  fontFamily: "JetBrains Mono, monospace", overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {e.other.label}
                </span>
                <span style={{ fontSize: 8, color: EDGE_COLOR[e.type] || T.textMuted,
                  fontFamily: "JetBrains Mono, monospace", flexShrink: 0 }}>
                  ← {e.type}
                </span>
              </button>
            ))}
          </div>
        )}
        {outgoing.length === 0 && incoming.length === 0 && (
          <p style={{ margin: "12px 14px", fontSize: 10, color: T.textMuted,
            fontFamily: "JetBrains Mono, monospace" }}>
            No connections recorded.
          </p>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function KnowledgeGraphPage() {
  const [graphData, setGraphData]     = useState({ nodes: [], edges: [] });
  const [loading, setLoading]         = useState(true);
  const [rebuilding, setRebuilding]   = useState(false);
  const [rebuildMsg, setRebuildMsg]   = useState("");
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTypes, setFilterTypes] = useState(new Set());
  const [projectFilter, setProjectFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchKnowledgeGraph();
      setGraphData(data.data || { nodes: [], edges: [] });
    } catch (e) {
      console.error("Knowledge graph load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleRebuild() {
    setRebuilding(true);
    setRebuildMsg("");
    try {
      const res = await rebuildKnowledgeGraph();
      if (res.ok) {
        const { counts } = res;
        setRebuildMsg(`Rebuilt: ${counts.projects}P ${counts.components}C ${counts.nodes}N ${counts.tasks}T ${counts.edges}E`);
        await load();
      } else {
        setRebuildMsg(`Error: ${res.error}`);
      }
    } catch (e) {
      setRebuildMsg(`Failed: ${e.message}`);
    } finally {
      setRebuilding(false);
    }
  }

  async function handleProjectFilter(name) {
    if (!name.trim()) { load(); setProjectFilter(""); return; }
    setProjectFilter(name);
    setLoading(true);
    try {
      const data = await fetchProjectGraph(name);
      setGraphData(data.data || { nodes: [], edges: [] });
    } catch (e) {
      console.error("Project graph load failed:", e);
    } finally {
      setLoading(false);
    }
  }

  function toggleType(t) {
    setFilterTypes(prev => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  }

  // Type counts for filter bar
  const typeCounts = {};
  for (const n of graphData.nodes) {
    typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
  }

  const visibleNodes = graphData.nodes.filter(n => {
    if (filterTypes.size > 0 && !filterTypes.has(n.type)) return false;
    if (searchQuery) return n.label.toLowerCase().includes(searchQuery.toLowerCase());
    return true;
  });

  const visibleEdges = graphData.edges.filter(e =>
    visibleNodes.some(n => n.id === e.source) &&
    visibleNodes.some(n => n.id === e.target)
  );

  return (
    <div style={{
      minHeight: "100vh", background: T.bg, color: T.text,
      fontFamily: "system-ui, sans-serif", display: "flex", flexDirection: "column",
    }}>
      {/* ── Header ── */}
      <header style={{
        borderBottom: `1px solid ${T.border}`, padding: "10px 16px",
        display: "flex", alignItems: "center", gap: 12, background: T.surface, flexShrink: 0,
      }}>
        <Link to="/" style={{
          fontSize: 10, color: T.goldDim, textDecoration: "none",
          border: `1px solid ${T.border}`, borderRadius: 3,
          padding: "3px 10px", fontFamily: "JetBrains Mono, monospace", letterSpacing: "0.05em",
        }}>
          ← SILVIA
        </Link>

        <div>
          <p style={{ margin: 0, fontSize: 9, color: T.textMuted, fontFamily: "JetBrains Mono, monospace",
            letterSpacing: "0.15em", textTransform: "uppercase" }}>
            SILVIA / Engineering Knowledge Graph
          </p>
          <h1 style={{ margin: 0, fontSize: 18, color: T.gold, fontFamily: "JetBrains Mono, monospace",
            fontWeight: 700, letterSpacing: "0.05em" }}>
            KNOWLEDGE GRAPH
          </h1>
        </div>

        {/* Stats */}
        <div style={{ display: "flex", gap: 16, marginLeft: 12 }}>
          {[
            { label: "Entities", value: graphData.nodes.length },
            { label: "Relationships", value: graphData.edges.length },
            { label: "Visible", value: visibleNodes.length },
          ].map(s => (
            <div key={s.label}>
              <p style={{ margin: 0, fontSize: 8, color: T.textMuted, fontFamily: "JetBrains Mono, monospace",
                textTransform: "uppercase", letterSpacing: "0.1em" }}>
                {s.label}
              </p>
              <p style={{ margin: 0, fontSize: 18, color: T.gold, fontFamily: "JetBrains Mono, monospace", fontWeight: 700 }}>
                {s.value}
              </p>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {rebuildMsg && (
            <span style={{ fontSize: 9, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
              {rebuildMsg}
            </span>
          )}
          <button onClick={load} style={btnStyle}>↻ Refresh</button>
          <button onClick={handleRebuild} disabled={rebuilding} style={{ ...btnStyle, borderColor: T.borderHi, color: T.gold }}>
            {rebuilding ? "Rebuilding…" : "⟳ Rebuild"}
          </button>
        </div>
      </header>

      {/* ── Filter bar ── */}
      <div style={{
        borderBottom: `1px solid ${T.border}`, padding: "7px 16px",
        display: "flex", gap: 8, alignItems: "center", background: "#060e1a", flexShrink: 0,
        flexWrap: "wrap",
      }}>
        {/* Search */}
        <input
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search nodes…"
          style={{
            background: "#080f1c", border: `1px solid ${T.border}`, borderRadius: 3,
            color: T.text, fontSize: 10, padding: "3px 8px",
            fontFamily: "JetBrains Mono, monospace", outline: "none", width: 160,
          }}
        />

        {/* Project focus */}
        <input
          value={projectFilter}
          onChange={e => setProjectFilter(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleProjectFilter(projectFilter)}
          placeholder="Focus project…"
          style={{
            background: "#080f1c", border: `1px solid ${T.border}`, borderRadius: 3,
            color: T.text, fontSize: 10, padding: "3px 8px",
            fontFamily: "JetBrains Mono, monospace", outline: "none", width: 140,
          }}
        />
        <button onClick={() => handleProjectFilter(projectFilter)} style={btnStyle}>Focus</button>
        {projectFilter && (
          <button onClick={() => { setProjectFilter(""); load(); }} style={btnStyle}>× All</button>
        )}

        {/* Type filters */}
        <span style={{ fontSize: 9, color: T.textMuted, fontFamily: "JetBrains Mono, monospace",
          letterSpacing: "0.05em", marginLeft: 4 }}>
          FILTER:
        </span>
        {ALL_TYPES.map(t => {
          const c = typeCounts[t] || 0;
          const active = filterTypes.has(t);
          const color = NODE_COLOR[t] || T.textMuted;
          return (
            <button key={t} onClick={() => toggleType(t)} style={{
              fontSize: 9, padding: "2px 7px", borderRadius: 12, cursor: "pointer",
              fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", letterSpacing: "0.04em",
              background: active ? `${color}22` : "none",
              border: `1px solid ${active ? color + "88" : T.border}`,
              color: active ? color : T.textMuted,
            }}>
              {t} {c > 0 ? `(${c})` : ""}
            </button>
          );
        })}
        {filterTypes.size > 0 && (
          <button onClick={() => setFilterTypes(new Set())} style={btnStyle}>× Clear</button>
        )}
      </div>

      {/* ── Main body ── */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* Canvas */}
        <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
          {loading && (
            <div style={{
              position: "absolute", inset: 0, display: "flex", alignItems: "center",
              justifyContent: "center", zIndex: 10, background: "rgba(6,11,20,0.7)",
            }}>
              <span style={{ fontSize: 12, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
                Loading graph…
              </span>
            </div>
          )}
          {!loading && graphData.nodes.length === 0 && (
            <div style={{
              position: "absolute", inset: 0, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 12,
            }}>
              <p style={{ fontSize: 12, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
                Knowledge graph is empty.
              </p>
              <button onClick={handleRebuild} disabled={rebuilding} style={{
                ...btnStyle, borderColor: T.borderHi, color: T.gold, fontSize: 11, padding: "6px 14px",
              }}>
                {rebuilding ? "Rebuilding…" : "⟳ Rebuild from data sources"}
              </button>
              <p style={{ fontSize: 10, color: T.textMuted, fontFamily: "JetBrains Mono, monospace", maxWidth: 320, textAlign: "center" }}>
                This will scan hardware projects, inventory, nodes, services, tasks, and orders to build the graph.
              </p>
            </div>
          )}
          <ForceGraph
            nodes={visibleNodes}
            edges={visibleEdges}
            selectedId={selectedNode?.id}
            onSelect={n => setSelectedNode(prev => prev?.id === n.id ? null : n)}
            filterTypes={filterTypes}
            searchQuery={searchQuery}
          />
        </div>

        {/* Node detail sidebar */}
        {selectedNode && (
          <NodeDetail
            node={selectedNode}
            edges={graphData.edges}
            allNodes={graphData.nodes}
            onClose={() => setSelectedNode(null)}
            onFocus={n => setSelectedNode(n)}
          />
        )}
      </div>

      {/* ── Legend ── */}
      <div style={{
        borderTop: `1px solid ${T.border}`, padding: "6px 16px",
        display: "flex", gap: 12, alignItems: "center",
        background: T.surface, flexShrink: 0, flexWrap: "wrap",
      }}>
        <span style={{ fontSize: 8, color: T.textMuted, fontFamily: "JetBrains Mono, monospace",
          textTransform: "uppercase", letterSpacing: "0.1em" }}>
          LEGEND:
        </span>
        {ALL_TYPES.filter(t => typeCounts[t]).map(t => (
          <span key={t} style={{ display: "flex", alignItems: "center", gap: 4,
            fontSize: 9, fontFamily: "JetBrains Mono, monospace", color: T.textMuted }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: NODE_COLOR[t] || "#888" }} />
            {t}
          </span>
        ))}
        <span style={{ marginLeft: "auto", fontSize: 9, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
          Scroll to zoom · Drag to pan · Click node to inspect · Drag node to move
        </span>
      </div>
    </div>
  );
}

const btnStyle = {
  background: "none", border: `1px solid ${T.border}`, color: T.textMuted,
  fontSize: 9, padding: "3px 9px", borderRadius: 3, cursor: "pointer",
  fontFamily: "JetBrains Mono, monospace",
};
