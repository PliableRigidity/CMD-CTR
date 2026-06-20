import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchBrain63Health, fetchBrain63Drafts, fetchBrain63Coverage,
  approveBrain63Draft, rejectBrain63Draft,
} from "../lib/api";

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

function Panel({ title, children, accent }) {
  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 6, padding: "14px 16px", marginBottom: 12,
      borderTop: accent ? `2px solid ${accent}` : undefined,
    }}>
      <div style={{ fontSize: "0.7rem", fontFamily: "JetBrains Mono, monospace", color: T.goldDim, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: "1.6rem", fontWeight: 700, color: color || T.gold, fontFamily: "JetBrains Mono, monospace" }}>{value}</div>
      <div style={{ fontSize: "0.65rem", color: T.textMuted, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function CoverageBar({ name, coverage, missing }) {
  const color = coverage === 100 ? T.success : coverage >= 60 ? T.warning : T.danger;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: 3 }}>
        <span style={{ color: T.text }}>{name}</span>
        <span style={{ color, fontFamily: "JetBrains Mono, monospace" }}>{coverage}%</span>
      </div>
      <div style={{ height: 4, background: "#1a2233", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${coverage}%`, background: color, borderRadius: 2, transition: "width 0.3s" }} />
      </div>
      {missing.length > 0 && (
        <div style={{ fontSize: "0.6rem", color: T.textMuted, marginTop: 2 }}>
          Missing: {missing.join(", ")}
        </div>
      )}
    </div>
  );
}

function DraftCard({ draft, onAction }) {
  const code = draft.code || "?";
  const title = draft.title || "";
  const desc = draft.description || "";
  return (
    <div style={{
      background: T.surfaceHi, border: `1px solid ${T.borderHi}`,
      borderRadius: 5, padding: "12px 14px", marginBottom: 8,
      borderLeft: `3px solid ${T.warning}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.75rem", color: T.gold, fontWeight: 600 }}>{code}</span>
        <span style={{ fontSize: "0.65rem", color: T.warning, fontFamily: "JetBrains Mono, monospace" }}>PENDING</span>
      </div>
      <div style={{ fontSize: "0.8rem", color: T.text, marginBottom: 4 }}>{title}</div>
      {desc && (
        <pre style={{
          fontSize: "0.65rem", color: T.textMuted, margin: "6px 0",
          whiteSpace: "pre-wrap", fontFamily: "JetBrains Mono, monospace",
          background: "#0a101c", padding: "6px 8px", borderRadius: 3,
          border: `1px solid ${T.border}`, maxHeight: 120, overflow: "auto",
        }}>
          {desc}
        </pre>
      )}
      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <button onClick={() => onAction("approve", code)} style={{
          background: `${T.success}22`, color: T.success, border: `1px solid ${T.success}44`,
          borderRadius: 4, padding: "4px 12px", fontSize: "0.7rem", cursor: "pointer",
          fontFamily: "JetBrains Mono, monospace",
        }}>Approve</button>
        <button onClick={() => onAction("reject", code)} style={{
          background: `${T.danger}22`, color: T.danger, border: `1px solid ${T.danger}44`,
          borderRadius: 4, padding: "4px 12px", fontSize: "0.7rem", cursor: "pointer",
          fontFamily: "JetBrains Mono, monospace",
        }}>Reject</button>
      </div>
    </div>
  );
}

export default function Brain63Page() {
  const [health, setHealth] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [h, d] = await Promise.all([fetchBrain63Health(), fetchBrain63Drafts()]);
      setHealth(h);
      setDrafts(Array.isArray(d) ? d : []);
    } catch (e) {
      console.error("Brain63 load failed:", e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (action, code) => {
    try {
      if (action === "approve") await approveBrain63Draft(code);
      else await rejectBrain63Draft(code);
      load();
    } catch (e) {
      console.error(`Brain63 ${action} failed:`, e);
    }
  };

  const projects = health?.projects || [];
  const needsUpdate = projects.filter(p => p.coverage < 100);
  const fullyDoc = projects.filter(p => p.coverage === 100);

  return (
    <div style={{
      minHeight: "100vh", background: T.bg, color: T.text,
      fontFamily: "'Inter', -apple-system, sans-serif",
      padding: "20px 24px",
    }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <Link to="/" style={{ color: T.goldDim, textDecoration: "none", fontSize: "0.7rem" }}>SILVIA</Link>
            <h1 style={{ margin: "4px 0 0", fontSize: "1.2rem", fontWeight: 600, color: T.gold }}>Brain63 Steward</h1>
          </div>
          <button onClick={load} style={{
            background: T.surfaceHi, color: T.textMuted, border: `1px solid ${T.border}`,
            borderRadius: 4, padding: "6px 12px", fontSize: "0.7rem", cursor: "pointer",
          }}>Refresh</button>
        </div>

        {loading ? (
          <div style={{ color: T.textMuted, textAlign: "center", padding: 40 }}>Loading…</div>
        ) : (
          <>
            <Panel title="Overview">
              <div style={{ display: "flex", justifyContent: "space-around" }}>
                <Stat label="Coverage" value={`${health?.overall_coverage || 0}%`} color={health?.overall_coverage >= 80 ? T.success : T.warning} />
                <Stat label="Projects" value={health?.total_projects || 0} />
                <Stat label="Files" value={health?.total_files || 0} />
                <Stat label="Missing" value={health?.total_missing || 0} color={health?.total_missing > 0 ? T.danger : T.success} />
                <Stat label="Pending Drafts" value={drafts.length} color={drafts.length > 0 ? T.warning : T.textMuted} />
              </div>
            </Panel>

            {drafts.length > 0 && (
              <Panel title="Pending Drafts" accent={T.warning}>
                {drafts.map(d => <DraftCard key={d.code || d.id} draft={d} onAction={handleAction} />)}
              </Panel>
            )}

            {needsUpdate.length > 0 && (
              <Panel title={`Needs Updates (${needsUpdate.length})`} accent={T.danger}>
                {needsUpdate.map(p => (
                  <CoverageBar key={p.name} name={p.name} coverage={p.coverage} missing={p.missing} />
                ))}
              </Panel>
            )}

            <Panel title={`Fully Documented (${fullyDoc.length})`} accent={T.success}>
              {fullyDoc.length === 0 ? (
                <div style={{ color: T.textMuted, fontSize: "0.8rem" }}>None</div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {fullyDoc.map(p => (
                    <span key={p.name} style={{
                      fontSize: "0.7rem", padding: "2px 8px", borderRadius: 3,
                      background: `${T.success}15`, color: T.success,
                      border: `1px solid ${T.success}33`,
                      fontFamily: "JetBrains Mono, monospace",
                    }}>
                      {p.name}
                    </span>
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}
