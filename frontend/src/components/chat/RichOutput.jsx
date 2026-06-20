import { useEffect, useRef, useState } from "react";

const T = {
  bg:        "#060b14",
  surface:   "#0d1623",
  surfaceHi: "#111e2e",
  border:    "rgba(201,148,58,0.18)",
  borderHi:  "rgba(201,148,58,0.45)",
  gold:      "#c9943a",
  goldDim:   "#8a6422",
  text:      "#ddd5c5",
  textMuted: "#6b7280",
  success:   "#00ff88",
  danger:    "#ff3b3b",
  info:      "#60a5fa",
  warning:   "#fbbf24",
};

function RichTable({ data }) {
  const { headers = [], rows = [], title = "", sources = [], stale = [] } = data;
  if (!rows.length) return <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>No data.</div>;

  const priorityColor = (val) => {
    const v = (val || "").toLowerCase();
    if (v === "buy now") return T.danger;
    if (v === "buy soon") return T.warning;
    if (v === "on order") return T.info;
    if (v === "owned") return T.success;
    return T.text;
  };

  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      {title && <div style={{ fontSize: "0.7rem", color: T.goldDim, marginBottom: 6, textTransform: "uppercase", letterSpacing: 1 }}>{title}</div>}
      {sources.length > 0 && <div style={{ fontSize: "0.6rem", color: T.textMuted, marginBottom: 8 }}>Sources: {sources.join(", ")}</div>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", borderSpacing: 0 }}>
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={i} style={{ textAlign: "left", padding: "6px 10px", borderBottom: `1px solid ${T.borderHi}`, color: T.gold, fontWeight: 600, fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: 0.5, whiteSpace: "nowrap" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} style={{ borderBottom: `1px solid ${T.border}` }}>
                {row.map((cell, ci) => (
                  <td key={ci} style={{ padding: "5px 10px", color: ci === 0 ? priorityColor(cell) : T.text, fontSize: "0.72rem" }}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stale.length > 0 && (
        <div style={{ marginTop: 10, padding: "6px 10px", background: `${T.warning}10`, border: `1px solid ${T.warning}30`, borderRadius: 4, fontSize: "0.65rem" }}>
          <div style={{ color: T.warning, fontWeight: 600, marginBottom: 3 }}>Stale Brain63 entries:</div>
          {stale.map((s, i) => <div key={i} style={{ color: T.textMuted }}>{s.name} — {s.note}</div>)}
        </div>
      )}
    </div>
  );
}

function MermaidRenderer({ data }) {
  const ref = useRef(null);
  const [svg, setSvg] = useState("");
  const { diagram = "", title = "" } = data;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { default: mermaid } = await import("mermaid");
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          themeVariables: {
            primaryColor: "#1a2740",
            primaryTextColor: T.text,
            primaryBorderColor: T.gold,
            lineColor: T.goldDim,
            secondaryColor: "#111e2e",
            tertiaryColor: "#0d1623",
          },
        });
        const id = `mermaid-${Date.now()}`;
        const { svg: rendered } = await mermaid.render(id, diagram);
        if (!cancelled) setSvg(rendered);
      } catch (e) {
        console.error("Mermaid render error:", e);
        if (!cancelled) setSvg("");
      }
    })();
    return () => { cancelled = true; };
  }, [diagram]);

  return (
    <div>
      {title && <div style={{ fontSize: "0.7rem", color: T.goldDim, marginBottom: 6, textTransform: "uppercase", letterSpacing: 1, fontFamily: "JetBrains Mono, monospace" }}>{title}</div>}
      {svg ? (
        <div ref={ref} dangerouslySetInnerHTML={{ __html: svg }} style={{ background: T.surface, padding: 12, borderRadius: 6, border: `1px solid ${T.border}`, overflowX: "auto" }} />
      ) : (
        <pre style={{ background: T.surface, padding: 12, borderRadius: 6, border: `1px solid ${T.border}`, fontSize: "0.72rem", color: T.text, overflowX: "auto", fontFamily: "JetBrains Mono, monospace" }}>
          {diagram}
        </pre>
      )}
    </div>
  );
}

function ChecklistRenderer({ data }) {
  const { title = "", phases = [] } = data;
  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      {title && <div style={{ fontSize: "0.7rem", color: T.goldDim, marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 }}>{title}</div>}
      {phases.map((phase, pi) => {
        const pct = phase.total ? Math.round(phase.done / phase.total * 100) : 0;
        return (
          <div key={pi} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <span style={{ color: T.gold, fontWeight: 600, fontSize: "0.72rem" }}>{phase.phase}</span>
              <span style={{ color: pct === 100 ? T.success : T.textMuted, fontSize: "0.65rem" }}>{pct}%</span>
            </div>
            <div style={{ height: 4, background: `${T.textMuted}30`, borderRadius: 2, marginBottom: 4 }}>
              <div style={{ width: `${pct}%`, height: "100%", background: pct === 100 ? T.success : T.gold, borderRadius: 2 }} />
            </div>
            {phase.items?.map((item, ii) => (
              <div key={ii} style={{ display: "flex", gap: 6, padding: "1px 0", color: item.checked ? T.textMuted : T.text }}>
                <span style={{ color: item.checked ? T.success : T.textMuted }}>{item.checked ? "✓" : "○"}</span>
                <span style={{ textDecoration: item.checked ? "line-through" : "none" }}>{item.name}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function MarkdownReport({ data }) {
  const { title = "", content = "" } = data;
  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      {title && <div style={{ fontSize: "0.7rem", color: T.goldDim, marginBottom: 6, textTransform: "uppercase", letterSpacing: 1 }}>{title}</div>}
      <pre style={{ whiteSpace: "pre-wrap", color: T.text, lineHeight: 1.5, fontSize: "0.72rem" }}>{content}</pre>
    </div>
  );
}

export default function RichOutput({ payload }) {
  const ro = payload?.rich_output;
  if (!ro) return null;

  const wrapStyle = {
    background: T.surface,
    border: `1px solid ${T.border}`,
    borderRadius: 6,
    padding: "12px 14px",
    marginTop: 8,
  };

  return (
    <div style={wrapStyle}>
      {ro.type === "table" && <RichTable data={ro} />}
      {ro.type === "mermaid" && <MermaidRenderer data={ro} />}
      {ro.type === "checklist" && <ChecklistRenderer data={ro} />}
      {ro.type === "markdown_report" && <MarkdownReport data={ro} />}
    </div>
  );
}
