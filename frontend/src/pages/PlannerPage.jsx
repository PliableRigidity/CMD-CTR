import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchPlannerTemplates, fetchPlannerRecommendations,
  fetchPlannerWhatCanIBuild, fetchPlannerBom,
  fetchPlannerGapAnalysis, fetchPlannerArchitecture,
  fetchPlannerProcurement, fetchPlannerRoadmap,
  fetchPlannerCanIBuild, createPlannerProject,
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
  cyan:      "#00e5ff",
};

function Panel({ title, children, span = 1, accent }) {
  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 6, padding: "14px 16px",
      gridColumn: `span ${span}`,
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

function DifficultyBadge({ level }) {
  const colors = { trivial: T.textMuted, easy: T.success, moderate: T.warning, hard: T.danger, expert: "#ff00ff", unknown: T.textMuted };
  return (
    <span style={{ fontSize: "0.6rem", padding: "1px 6px", borderRadius: 3, border: `1px solid ${colors[level] || T.textMuted}40`, color: colors[level] || T.textMuted, fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase" }}>
      {level}
    </span>
  );
}

function ReadinessBar({ pct }) {
  const color = pct >= 80 ? T.success : pct >= 40 ? T.warning : T.danger;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
      <div style={{ flex: 1, height: 6, background: `${T.textMuted}30`, borderRadius: 3 }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.4s" }} />
      </div>
      <span style={{ fontSize: "0.7rem", color, fontFamily: "JetBrains Mono, monospace", minWidth: 32 }}>{pct}%</span>
    </div>
  );
}

// ── Views ────────────────────────────────────────────────────────────────────

function TemplatesView({ templates }) {
  if (!templates?.length) return <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>No templates available.</div>;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
      {templates.map((t) => (
        <div key={t.id} style={{ background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 6, padding: "12px 14px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontWeight: 600, color: T.text, fontSize: "0.82rem" }}>{t.name}</span>
            <DifficultyBadge level={t.difficulty} />
          </div>
          <div style={{ fontSize: "0.72rem", color: T.textMuted, marginBottom: 8 }}>{t.description}</div>
          <div style={{ display: "flex", gap: 12, fontSize: "0.65rem", color: T.goldDim }}>
            <span>{t.phase_count} phases</span>
            <span>{t.total_items} items</span>
          </div>
          <div style={{ marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
            {t.tags.map((tag) => (
              <span key={tag} style={{ fontSize: "0.58rem", padding: "1px 5px", background: `${T.gold}15`, border: `1px solid ${T.gold}25`, borderRadius: 3, color: T.goldDim }}>{tag}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function IdeasView({ ideas }) {
  if (!ideas) return <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>Loading...</div>;
  const { suggestions = [], custom_ideas = [], inventory_count = 0 } = ideas;
  return (
    <div>
      <div style={{ fontSize: "0.72rem", color: T.textMuted, marginBottom: 12 }}>
        {inventory_count} parts in inventory. {suggestions.length} template match(es), {custom_ideas.length} custom idea(s).
      </div>
      {suggestions.length > 0 && (
        <Panel title="Template Matches">
          {suggestions.map((s, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: `1px solid ${T.border}` }}>
              <div>
                <span style={{ color: T.text, fontWeight: 600, fontSize: "0.78rem" }}>{s.name}</span>
                <DifficultyBadge level={s.difficulty} />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ReadinessBar pct={s.match_pct} />
                <span style={{ fontSize: "0.65rem", color: T.textMuted }}>{s.matched_items?.length || 0} matched, {s.missing_items?.length || 0} missing</span>
              </div>
            </div>
          ))}
        </Panel>
      )}
      {custom_ideas.length > 0 && (
        <Panel title="Custom Ideas from Inventory">
          {custom_ideas.map((c, i) => (
            <div key={i} style={{ padding: "5px 0", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: T.text, fontSize: "0.78rem" }}>{c.name}</span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <DifficultyBadge level={c.difficulty} />
                <span style={{ fontSize: "0.65rem", color: T.textMuted }}>{c.reason}</span>
              </div>
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}

function ProjectDetailView({ project, setProject }) {
  const [bom, setBom] = useState(null);
  const [gap, setGap] = useState(null);
  const [arch, setArch] = useState(null);
  const [roadmap, setRoadmap] = useState(null);
  const [procurement, setProcurement] = useState(null);
  const [buildable, setBuildable] = useState(null);
  const [tab, setTab] = useState("bom");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!project) return;
    setLoading(true);
    Promise.all([
      fetchPlannerBom(project).catch(() => null),
      fetchPlannerGapAnalysis(project).catch(() => null),
      fetchPlannerArchitecture(project).catch(() => null),
      fetchPlannerRoadmap(project).catch(() => null),
      fetchPlannerProcurement(project).catch(() => null),
      fetchPlannerCanIBuild(project).catch(() => null),
    ]).then(([b, g, a, r, p, c]) => {
      setBom(b);
      setGap(g);
      setArch(a);
      setRoadmap(r);
      setProcurement(p);
      setBuildable(c);
      setLoading(false);
    });
  }, [project]);

  if (!project) return null;

  const tabs = [
    { id: "bom", label: "BOM" },
    { id: "gap", label: "Gap" },
    { id: "arch", label: "Architecture" },
    { id: "roadmap", label: "Roadmap" },
    { id: "procurement", label: "Procurement" },
  ];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <button onClick={() => setProject(null)} style={{ background: "none", border: `1px solid ${T.border}`, color: T.goldDim, borderRadius: 4, padding: "3px 8px", cursor: "pointer", fontSize: "0.7rem" }}>Back</button>
        <span style={{ color: T.gold, fontWeight: 700, fontSize: "1rem" }}>{project}</span>
        {buildable?.ok && (
          <span style={{ fontSize: "0.72rem", padding: "2px 8px", borderRadius: 4, border: `1px solid ${buildable.can_build ? T.success : T.warning}40`, color: buildable.can_build ? T.success : T.warning }}>
            {buildable.verdict} — {buildable.readiness_pct}% ready
          </span>
        )}
      </div>
      <div style={{ display: "flex", gap: 4, marginBottom: 14, borderBottom: `1px solid ${T.border}`, paddingBottom: 8 }}>
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            background: tab === t.id ? `${T.gold}20` : "transparent",
            border: `1px solid ${tab === t.id ? T.borderHi : T.border}`,
            color: tab === t.id ? T.gold : T.textMuted,
            borderRadius: 4, padding: "4px 10px", cursor: "pointer",
            fontSize: "0.68rem", fontFamily: "JetBrains Mono, monospace",
          }}>
            {t.label}
          </button>
        ))}
      </div>
      {loading ? <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>Loading...</div> : (
        <>
          {tab === "bom" && bom?.ok && <BomPanel data={bom} />}
          {tab === "gap" && gap?.ok && <GapPanel data={gap} />}
          {tab === "arch" && arch?.ok && <ArchPanel data={arch} />}
          {tab === "roadmap" && roadmap?.ok && <RoadmapPanel data={roadmap} />}
          {tab === "procurement" && procurement?.ok && <ProcurementPanel data={procurement} />}
          {!loading && tab === "bom" && !bom?.ok && <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>{bom?.error || "No BOM data."}</div>}
          {!loading && tab === "gap" && !gap?.ok && <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>{gap?.error || "No gap data."}</div>}
          {!loading && tab === "arch" && !arch?.ok && <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>{arch?.error || "No architecture data."}</div>}
          {!loading && tab === "roadmap" && !roadmap?.ok && <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>{roadmap?.error || "No roadmap data."}</div>}
          {!loading && tab === "procurement" && !procurement?.ok && <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>{procurement?.error || "No procurement data."}</div>}
        </>
      )}
    </div>
  );
}

function BomPanel({ data }) {
  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      <div style={{ display: "flex", gap: 20, marginBottom: 12 }}>
        <Stat label="Total" value={data.total} />
        <Stat label="Available" value={data.available} color={T.success} />
        <Stat label="Missing" value={data.missing} color={T.danger} />
        <Stat label="Ready" value={`${data.readiness_pct}%`} color={data.readiness_pct >= 80 ? T.success : T.warning} />
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Status", "Component", "Phase"].map((h) => (
              <th key={h} style={{ textAlign: "left", padding: "5px 8px", borderBottom: `1px solid ${T.borderHi}`, color: T.gold, fontSize: "0.65rem", textTransform: "uppercase" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.bom?.map((item, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
              <td style={{ padding: "4px 8px", color: item.available ? T.success : T.danger }}>{item.available ? "Owned" : "Missing"}</td>
              <td style={{ padding: "4px 8px", color: T.text }}>{item.component}</td>
              <td style={{ padding: "4px 8px", color: T.textMuted }}>{item.phase || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GapPanel({ data }) {
  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      <div style={{ marginBottom: 10, color: T.text }}>{data.summary}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <div style={{ color: T.success, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 6 }}>Owned ({data.owned_count})</div>
          {data.owned?.map((item, i) => <div key={i} style={{ padding: "2px 0", color: T.textMuted }}>✓ {item.component}</div>)}
        </div>
        <div>
          <div style={{ color: T.danger, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 6 }}>Missing ({data.missing_count})</div>
          {data.missing?.map((item, i) => <div key={i} style={{ padding: "2px 0", color: T.text }}>✗ {item.component}</div>)}
        </div>
      </div>
    </div>
  );
}

function ArchPanel({ data }) {
  const arch = data.architecture || {};
  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      {arch.purpose && <div style={{ color: T.text, marginBottom: 10 }}>{arch.purpose}</div>}
      {data.difficulty && data.difficulty !== "unknown" && (
        <div style={{ marginBottom: 8 }}>Difficulty: <DifficultyBadge level={data.difficulty} /></div>
      )}
      {arch.components?.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: T.gold, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 4 }}>Components</div>
          {arch.components.map((c, i) => <div key={i} style={{ padding: "2px 0", color: T.text }}>• {c}</div>)}
        </div>
      )}
      {arch.connections && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: T.gold, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 4 }}>Connections</div>
          <div style={{ color: T.textMuted }}>{arch.connections}</div>
        </div>
      )}
      {arch.firmware?.length > 0 && (
        <div>
          <div style={{ color: T.gold, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 4 }}>Firmware / Software</div>
          {arch.firmware.map((f, i) => <div key={i} style={{ padding: "2px 0", color: T.textMuted }}>• {f}</div>)}
        </div>
      )}
    </div>
  );
}

function RoadmapPanel({ data }) {
  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      <div style={{ color: T.textMuted, marginBottom: 10 }}>{data.total_phases} phases, {data.total_items} items, {data.completed_items} completed</div>
      {data.phases?.map((phase, pi) => {
        const pct = phase.total ? Math.round(phase.done / phase.total * 100) : 0;
        return (
          <div key={pi} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <span style={{ color: T.gold, fontWeight: 600, fontSize: "0.72rem" }}>{phase.name}</span>
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

function ProcurementPanel({ data }) {
  const { buy_now = [], buy_soon = [], optional = [] } = data;
  if (!buy_now.length && !buy_soon.length && !optional.length) {
    return <div style={{ color: T.success, fontSize: "0.75rem" }}>All parts accounted for.</div>;
  }
  return (
    <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
      <div style={{ color: T.textMuted, marginBottom: 10 }}>{data.summary}</div>
      {buy_now.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: T.danger, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 4 }}>Buy Now ({buy_now.length})</div>
          {buy_now.map((item, i) => <div key={i} style={{ padding: "2px 0", color: T.text }}>• {item.component}</div>)}
        </div>
      )}
      {buy_soon.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: T.warning, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 4 }}>Buy Soon ({buy_soon.length})</div>
          {buy_soon.map((item, i) => <div key={i} style={{ padding: "2px 0", color: T.text }}>• {item.component}</div>)}
        </div>
      )}
      {optional.length > 0 && (
        <div>
          <div style={{ color: T.textMuted, fontSize: "0.68rem", textTransform: "uppercase", marginBottom: 4 }}>Optional ({optional.length})</div>
          {optional.map((item, i) => <div key={i} style={{ padding: "2px 0", color: T.textMuted }}>• {item.component}</div>)}
        </div>
      )}
    </div>
  );
}

function RecommendationsView({ recs }) {
  if (!recs) return <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>Loading...</div>;
  const { template_matches = [], custom_ideas = [], existing_ready = [] } = recs;
  return (
    <div>
      {existing_ready.length > 0 && (
        <Panel title="Ready to Build" accent={T.success}>
          {existing_ready.map((p, i) => (
            <div key={i} style={{ padding: "5px 0", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: T.text, fontSize: "0.78rem" }}>{p.name}</span>
              <ReadinessBar pct={p.readiness_pct} />
            </div>
          ))}
        </Panel>
      )}
      {template_matches.length > 0 && (
        <Panel title="Template Matches">
          {template_matches.map((s, i) => (
            <div key={i} style={{ padding: "5px 0", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ color: T.text, fontSize: "0.78rem" }}>{s.name} <DifficultyBadge level={s.difficulty} /></span>
              <ReadinessBar pct={s.match_pct} />
            </div>
          ))}
        </Panel>
      )}
      {custom_ideas.length > 0 && (
        <Panel title="Custom Ideas">
          {custom_ideas.map((c, i) => (
            <div key={i} style={{ padding: "4px 0", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: T.text, fontSize: "0.78rem" }}>{c.name}</span>
              <span style={{ fontSize: "0.65rem", color: T.textMuted }}>{c.reason}</span>
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function PlannerPage() {
  const [view, setView] = useState("recommendations");
  const [templates, setTemplates] = useState([]);
  const [ideas, setIdeas] = useState(null);
  const [recs, setRecs] = useState(null);
  const [selectedProject, setSelectedProject] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (view === "recommendations") {
        const r = await fetchPlannerRecommendations();
        setRecs(r);
      } else if (view === "templates") {
        const t = await fetchPlannerTemplates();
        setTemplates(t?.templates || []);
      } else if (view === "ideas") {
        const i = await fetchPlannerWhatCanIBuild();
        setIdeas(i);
      }
    } catch (e) {
      console.error("PlannerPage load error:", e);
    }
    setLoading(false);
  }, [view]);

  useEffect(() => { load(); }, [load]);

  const navStyle = (v) => ({
    padding: "6px 14px", borderRadius: 4, cursor: "pointer",
    fontSize: "0.72rem", fontFamily: "JetBrains Mono, monospace",
    background: view === v ? `${T.gold}20` : "transparent",
    border: `1px solid ${view === v ? T.borderHi : T.border}`,
    color: view === v ? T.gold : T.textMuted,
  });

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text, padding: "20px 28px", fontFamily: "'JetBrains Mono', monospace" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <Link to="/" style={{ color: T.goldDim, textDecoration: "none", fontSize: "0.7rem" }}>CMD-CTR</Link>
          <span style={{ color: T.goldDim, margin: "0 6px", fontSize: "0.7rem" }}>/</span>
          <span style={{ color: T.gold, fontWeight: 700, fontSize: "0.85rem" }}>Engineering Planner</span>
        </div>
      </div>

      {/* If a project is selected, show detail view */}
      {selectedProject ? (
        <ProjectDetailView project={selectedProject} setProject={setSelectedProject} />
      ) : (
        <>
          {/* Nav */}
          <div style={{ display: "flex", gap: 6, marginBottom: 18 }}>
            <button onClick={() => setView("recommendations")} style={navStyle("recommendations")}>Recommendations</button>
            <button onClick={() => setView("templates")} style={navStyle("templates")}>Templates</button>
            <button onClick={() => setView("ideas")} style={navStyle("ideas")}>What Can I Build</button>
          </div>

          {/* Quick project lookup */}
          <div style={{ marginBottom: 18 }}>
            <form onSubmit={(e) => {
              e.preventDefault();
              const val = e.target.elements.project.value.trim();
              if (val) setSelectedProject(val);
            }} style={{ display: "flex", gap: 8 }}>
              <input name="project" placeholder="Explore project (name or template)..." style={{
                flex: 1, background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 4,
                padding: "6px 10px", color: T.text, fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace",
                outline: "none",
              }} />
              <button type="submit" style={{
                background: `${T.gold}20`, border: `1px solid ${T.borderHi}`, borderRadius: 4,
                padding: "6px 14px", color: T.gold, cursor: "pointer", fontSize: "0.72rem",
                fontFamily: "JetBrains Mono, monospace",
              }}>Explore</button>
            </form>
          </div>

          {/* View Content */}
          {loading ? <div style={{ color: T.textMuted, fontSize: "0.75rem" }}>Loading...</div> : (
            <>
              {view === "recommendations" && <RecommendationsView recs={recs} />}
              {view === "templates" && <TemplatesView templates={templates} />}
              {view === "ideas" && <IdeasView ideas={ideas} />}
            </>
          )}
        </>
      )}
    </div>
  );
}
