import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchWorkspaceStatus, fetchWorkspacePriorities,
  fetchWorkspaceBriefing, fetchWorkspaceBlocked,
  fetchWorkspaceReady, fetchWorkspaceRecommendations,
  fetchWorkspaceOrderRecommendations,
  fetchWorkspaceContext, fetchRecentContextProjects,
  fetchWorkspaceSessions, fetchWorkspaceAccomplishments,
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
      <div style={{ fontSize: "1.6rem", fontWeight: 700, color: color || T.gold, fontFamily: "JetBrains Mono, monospace" }}>
        {value}
      </div>
      <div style={{ fontSize: "0.65rem", color: T.textMuted, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function PriorityBar({ score, max = 120 }) {
  const pct = Math.min(100, (score / max) * 100);
  const color = pct > 70 ? T.success : pct > 40 ? T.warning : T.danger;
  return (
    <div style={{ flex: 1, height: 6, background: `${T.textMuted}30`, borderRadius: 3 }}>
      <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.4s" }} />
    </div>
  );
}

export default function WorkspacePage() {
  const [view, setView] = useState("overview");
  const [status, setStatus] = useState(null);
  const [priorities, setPriorities] = useState([]);
  const [briefing, setBriefing] = useState(null);
  const [blocked, setBlocked] = useState([]);
  const [ready, setReady] = useState([]);
  const [recommendation, setRecommendation] = useState(null);
  const [orders, setOrders] = useState(null);
  const [context, setContext] = useState(null);
  const [recentProjects, setRecentProjects] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [accomplishments, setAccomplishments] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (view === "overview") {
        const [s, p, r, rec] = await Promise.all([
          fetchWorkspaceStatus(),
          fetchWorkspacePriorities(),
          fetchWorkspaceReady(),
          fetchWorkspaceRecommendations(),
        ]);
        setStatus(s); setPriorities(p); setReady(r); setRecommendation(rec);
      } else if (view === "briefing") {
        const b = await fetchWorkspaceBriefing();
        setBriefing(b);
      } else if (view === "blocked") {
        const b = await fetchWorkspaceBlocked();
        setBlocked(b);
      } else if (view === "orders") {
        const o = await fetchWorkspaceOrderRecommendations();
        setOrders(o);
      } else if (view === "context") {
        const [c, rp] = await Promise.all([
          fetchWorkspaceContext(),
          fetchRecentContextProjects(24),
        ]);
        setContext(c);
        setRecentProjects(rp || []);
      } else if (view === "sessions") {
        const [s, a] = await Promise.all([
          fetchWorkspaceSessions(48, 20),
          fetchWorkspaceAccomplishments(24),
        ]);
        setSessions(s || []);
        setAccomplishments(a);
      }
    } catch (e) { console.error("Workspace load error:", e); }
    setLoading(false);
  }, [view]);

  useEffect(() => { load(); }, [load]);

  const views = [
    { id: "overview", label: "Overview" },
    { id: "context",  label: "Context" },
    { id: "sessions", label: "Sessions" },
    { id: "briefing", label: "Briefing" },
    { id: "blocked",  label: "Blocked" },
    { id: "orders",   label: "Orders" },
  ];

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text, fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 24px", borderBottom: `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Link to="/" style={{ color: T.goldDim, textDecoration: "none", fontSize: "0.75rem" }}>SILVIA</Link>
          <span style={{ color: T.goldDim, fontSize: "0.6rem" }}>/</span>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.85rem", color: T.gold, fontWeight: 600 }}>WORKSPACE DIGITAL TWIN</span>
        </div>
        <button onClick={load} style={{ background: "none", border: `1px solid ${T.border}`, color: T.goldDim, padding: "4px 12px", borderRadius: 4, cursor: "pointer", fontSize: "0.7rem", fontFamily: "JetBrains Mono, monospace" }}>
          {loading ? "..." : "Refresh"}
        </button>
      </div>

      {/* View tabs */}
      <div style={{ display: "flex", gap: 0, padding: "0 24px", borderBottom: `1px solid ${T.border}` }}>
        {views.map(v => (
          <button key={v.id} onClick={() => setView(v.id)} style={{
            background: "none", border: "none", padding: "10px 18px", cursor: "pointer",
            color: view === v.id ? T.gold : T.textMuted,
            borderBottom: view === v.id ? `2px solid ${T.gold}` : "2px solid transparent",
            fontFamily: "JetBrains Mono, monospace", fontSize: "0.72rem", fontWeight: view === v.id ? 600 : 400,
          }}>
            {v.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: "20px 24px" }}>
        {loading && <div style={{ color: T.textMuted, fontFamily: "JetBrains Mono, monospace", fontSize: "0.75rem" }}>Loading workspace state...</div>}
        {!loading && view === "overview" && status && <OverviewView status={status} priorities={priorities} ready={ready} recommendation={recommendation} />}
        {!loading && view === "context" && <ContextView context={context} recentProjects={recentProjects} onRefresh={load} />}
        {!loading && view === "sessions" && <SessionsView sessions={sessions} accomplishments={accomplishments} />}
        {!loading && view === "briefing" && briefing && <BriefingView data={briefing} />}
        {!loading && view === "blocked" && <BlockedView blocked={blocked} />}
        {!loading && view === "orders" && orders && <OrdersView data={orders} />}
      </div>
    </div>
  );
}

function OverviewView({ status, priorities, ready, recommendation }) {
  const s = status?.summary || {};
  const top = status?.priority_project;
  const rec = recommendation?.recommendation;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
      {/* Stats row */}
      <Panel title="Projects" accent={T.gold}>
        <div style={{ display: "flex", justifyContent: "space-around" }}>
          <Stat label="Total" value={s.total_projects || 0} />
          <Stat label="Active" value={s.active || 0} color={T.success} />
          <Stat label="Blocked" value={s.blocked || 0} color={s.blocked ? T.danger : T.textMuted} />
          <Stat label="Ready" value={s.ready || 0} color={T.cyan} />
        </div>
      </Panel>

      <Panel title="Infrastructure" accent={T.info}>
        <div style={{ display: "flex", justifyContent: "space-around" }}>
          <Stat label="Online" value={s.nodes_online || 0} color={T.success} />
          <Stat label="Total" value={s.nodes_total || 0} />
          <Stat label="Alerts" value={s.active_alerts || 0} color={s.active_alerts ? T.warning : T.textMuted} />
        </div>
      </Panel>

      <Panel title="Activity" accent={T.success}>
        <div style={{ display: "flex", justifyContent: "space-around" }}>
          <Stat label="Tasks" value={s.pending_tasks || 0} />
          <Stat label="Orders" value={s.open_orders || 0} color={s.open_orders ? T.warning : T.textMuted} />
          <Stat label="Actions" value={s.recent_actions || 0} color={T.info} />
        </div>
      </Panel>

      {/* Recommendation */}
      {rec && (
        <Panel title="Recommended Work" span={2} accent={T.success}>
          <div style={{ fontSize: "1.1rem", fontWeight: 600, color: T.gold, marginBottom: 6 }}>{rec.project}</div>
          <div style={{ display: "flex", gap: 16, marginBottom: 8, fontSize: "0.75rem", color: T.textMuted }}>
            <span>Score: <span style={{ color: T.text }}>{rec.score}</span></span>
            <span>Readiness: <span style={{ color: T.text }}>{rec.readiness_pct}%</span></span>
            <span>Status: <span style={{ color: T.text }}>{rec.status}</span></span>
          </div>
          {rec.reasons?.length > 0 && (
            <div style={{ fontSize: "0.72rem", color: T.text, marginBottom: 6 }}>
              {rec.reasons.map((r, i) => <div key={i} style={{ marginBottom: 2 }}>• {r}</div>)}
            </div>
          )}
          {rec.suggested_tasks?.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: "0.65rem", color: T.goldDim, marginBottom: 4 }}>SUGGESTED TASKS</div>
              {rec.suggested_tasks.map((t, i) => (
                <div key={i} style={{ fontSize: "0.72rem", color: T.text, paddingLeft: 8 }}>{i + 1}. {t}</div>
              ))}
            </div>
          )}
          {rec.recommended_action && (
            <div style={{ marginTop: 8, fontSize: "0.72rem", color: T.success }}>→ {rec.recommended_action}</div>
          )}
        </Panel>
      )}

      {/* Ready projects */}
      <Panel title="Ready to Build">
        {ready.length === 0 ? (
          <div style={{ fontSize: "0.72rem", color: T.textMuted }}>No projects fully ready.</div>
        ) : ready.map((p, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: `1px solid ${T.border}` }}>
            <span style={{ fontSize: "0.75rem" }}>{p.name}</span>
            <span style={{ fontSize: "0.65rem", color: T.success }}>{p.readiness_pct}%</span>
          </div>
        ))}
      </Panel>

      {/* Priority ranking */}
      <Panel title="Project Rankings" span={3}>
        <div style={{ display: "grid", gap: 8 }}>
          {priorities.map((p, i) => (
            <div key={p.name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 0", borderBottom: `1px solid ${T.border}` }}>
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.75rem", color: T.goldDim, width: 24, textAlign: "right" }}>{i + 1}.</span>
              <span style={{ fontSize: "0.8rem", fontWeight: 500, minWidth: 120 }}>{p.name}</span>
              <PriorityBar score={p.score} />
              <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.7rem", color: T.text, minWidth: 36, textAlign: "right" }}>{p.score}</span>
              <span style={{ fontSize: "0.6rem", color: T.textMuted, minWidth: 50 }}>{p.readiness_pct}% rdy</span>
              <span style={{ fontSize: "0.6rem", color: p.status === "active" ? T.success : p.status === "blocked" ? T.danger : T.textMuted, minWidth: 55 }}>{p.status}</span>
              {p.blockers?.length > 0 && <span style={{ fontSize: "0.6rem", color: T.danger }}>{p.blockers.length} blocker{p.blockers.length !== 1 ? "s" : ""}</span>}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function BriefingView({ data }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
      <Panel title="Workspace" span={2} accent={T.gold}>
        <div style={{ fontSize: "1rem", fontWeight: 500, color: T.text, marginBottom: 8 }}>{data.greeting}</div>
        <div style={{ display: "flex", gap: 24, fontSize: "0.75rem" }}>
          <span>{data.workspace?.projects} projects</span>
          <span style={{ color: T.success }}>{data.workspace?.active} active</span>
          <span style={{ color: data.workspace?.blocked ? T.danger : T.textMuted }}>{data.workspace?.blocked} blocked</span>
          <span style={{ color: T.cyan }}>{data.workspace?.ready} ready</span>
          <span>{data.infrastructure?.nodes_online} nodes online</span>
        </div>
      </Panel>

      {data.top_priority && (
        <Panel title="Top Priority" accent={T.success}>
          <div style={{ fontSize: "1rem", fontWeight: 600, color: T.gold }}>{data.top_priority.name}</div>
          <div style={{ fontSize: "0.72rem", color: T.textMuted, marginTop: 4 }}>
            Score: {data.top_priority.score} | Readiness: {data.top_priority.readiness_pct}%
          </div>
          <div style={{ fontSize: "0.72rem", color: T.success, marginTop: 4 }}>→ {data.top_priority.recommended_action}</div>
        </Panel>
      )}

      <Panel title="Priority Ranking" accent={T.info}>
        {data.priorities?.map((p, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: "0.72rem" }}>
            <span>{p.rank}. {p.name}</span>
            <span style={{ color: T.textMuted }}>{p.score} / {p.readiness_pct}%</span>
          </div>
        ))}
      </Panel>

      {data.blocked_projects?.length > 0 && (
        <Panel title="Blocked" accent={T.danger}>
          {data.blocked_projects.map((b, i) => (
            <div key={i} style={{ marginBottom: 6 }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 500 }}>{b.name}</div>
              {b.blockers?.map((bl, j) => (
                <div key={j} style={{ fontSize: "0.65rem", color: T.danger, paddingLeft: 8 }}>— {bl}</div>
              ))}
            </div>
          ))}
        </Panel>
      )}

      {data.pending_orders?.length > 0 && (
        <Panel title="Pending Orders" accent={T.warning}>
          {data.pending_orders.map((o, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", padding: "2px 0" }}>
              <span>{o.part_name}</span>
              <span style={{ color: T.textMuted }}>{o.status}</span>
            </div>
          ))}
        </Panel>
      )}

      {data.high_priority_tasks?.length > 0 && (
        <Panel title="High Priority Tasks">
          {data.high_priority_tasks.map((t, i) => (
            <div key={i} style={{ fontSize: "0.72rem", padding: "2px 0" }}>
              {t.title} {t.project && <span style={{ color: T.textMuted }}>[{t.project}]</span>}
            </div>
          ))}
        </Panel>
      )}

      {data.active_alerts?.length > 0 && (
        <Panel title="Active Alerts" accent={T.danger}>
          {data.active_alerts.map((a, i) => (
            <div key={i} style={{ fontSize: "0.72rem", padding: "2px 0", color: a.severity === "critical" ? T.danger : T.warning }}>
              [{a.severity.toUpperCase()}] {a.message}
            </div>
          ))}
        </Panel>
      )}

      {data.recent_changes?.length > 0 && (
        <Panel title="Recent Changes">
          {data.recent_changes.map((c, i) => (
            <div key={i} style={{ fontSize: "0.72rem", padding: "2px 0", color: T.textMuted }}>
              {c.intent || c.message}
            </div>
          ))}
        </Panel>
      )}

      {data.recent_memories?.length > 0 && (
        <Panel title="Recent Memories">
          {data.recent_memories.map((m, i) => (
            <div key={i} style={{ fontSize: "0.72rem", padding: "2px 0" }}>
              <span style={{ color: T.info }}>[{m.type}]</span> {m.title} <span style={{ color: T.textMuted }}>({m.project})</span>
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}

function BlockedView({ blocked }) {
  if (!blocked.length) {
    return <div style={{ color: T.textMuted, fontSize: "0.8rem", fontFamily: "JetBrains Mono, monospace" }}>No projects are currently blocked.</div>;
  }
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {blocked.map((p, i) => (
        <Panel key={i} title={p.name} accent={T.danger}>
          <div style={{ display: "flex", gap: 12, fontSize: "0.72rem", marginBottom: 6 }}>
            <span>Priority: <span style={{ color: T.text }}>{p.priority}</span></span>
            <span>Readiness: <span style={{ color: T.text }}>{p.readiness_pct}%</span></span>
          </div>
          {p.blockers?.map((b, j) => (
            <div key={j} style={{ fontSize: "0.72rem", color: T.danger, padding: "2px 0", paddingLeft: 8 }}>
              — {b.description}
            </div>
          ))}
        </Panel>
      ))}
    </div>
  );
}

function ContextView({ context, recentProjects, onRefresh }) {
  if (!context) return <div style={{ color: T.textMuted, fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>No context data.</div>;

  const sessionColor = {
    "Development Session": T.info,
    "PCB Design Session": T.warning,
    "CAD Session": T.warning,
    "3D Printing Session": T.cyan,
    "Research Session": T.gold,
    "Procurement Session": T.success,
    "Media Session": T.textMuted,
    "Communication": T.textMuted,
    "General": T.textMuted,
  };

  const eng = context.engineering_context || {};
  const tools = context.open_tools || [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
      {/* Current Activity */}
      <Panel title="Current Activity" span={2} accent={sessionColor[context.session_type] || T.gold}>
        <div style={{ display: "flex", gap: 20, marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: "0.65rem", color: T.goldDim, textTransform: "uppercase", marginBottom: 2 }}>Session</div>
            <div style={{ fontSize: "0.9rem", fontWeight: 600, color: sessionColor[context.session_type] || T.text }}>{context.session_type || "—"}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.65rem", color: T.goldDim, textTransform: "uppercase", marginBottom: 2 }}>Active App</div>
            <div style={{ fontSize: "0.9rem", fontWeight: 600, color: T.text }}>{context.active_app || "—"}</div>
          </div>
          {context.project && (
            <div>
              <div style={{ fontSize: "0.65rem", color: T.goldDim, textTransform: "uppercase", marginBottom: 2 }}>Project</div>
              <div style={{ fontSize: "0.9rem", fontWeight: 600, color: T.gold }}>{context.project}</div>
            </div>
          )}
        </div>
        {context.file && (
          <div style={{ fontSize: "0.75rem", color: T.text, marginBottom: 4 }}>
            <span style={{ color: T.goldDim }}>File:</span> {context.file}
            {eng.language && <span style={{ color: T.textMuted, marginLeft: 8 }}>({eng.language})</span>}
          </div>
        )}
        {context.workspace && context.workspace !== context.project && (
          <div style={{ fontSize: "0.75rem", color: T.textMuted }}>
            <span style={{ color: T.goldDim }}>Workspace:</span> {context.workspace}
          </div>
        )}
        {eng.site && (
          <div style={{ fontSize: "0.75rem", color: T.text, marginTop: 4 }}>
            <span style={{ color: T.goldDim }}>Site:</span> {eng.site}
            {eng.activity && <span style={{ color: T.textMuted, marginLeft: 8 }}>({eng.activity})</span>}
          </div>
        )}
        {eng.kicad_tool && (
          <div style={{ fontSize: "0.75rem", color: T.text, marginTop: 4 }}>
            <span style={{ color: T.goldDim }}>KiCad:</span> {eng.kicad_tool}
          </div>
        )}
        <button onClick={onRefresh} style={{
          marginTop: 10, background: "none", border: `1px solid ${T.border}`, color: T.goldDim,
          padding: "3px 10px", borderRadius: 4, cursor: "pointer", fontSize: "0.65rem",
          fontFamily: "JetBrains Mono, monospace",
        }}>Refresh Context</button>
      </Panel>

      {/* Open Tools */}
      <Panel title={`Open Tools (${tools.length})`} accent={T.info}>
        {tools.length === 0 ? (
          <div style={{ color: T.textMuted, fontSize: "0.72rem" }}>No engineering tools detected.</div>
        ) : tools.map((t, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: `1px solid ${T.border}` }}>
            <span style={{ fontSize: "0.75rem", color: T.text }}>{t.app_name}</span>
            <span style={{ fontSize: "0.6rem", color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>{t.category}</span>
          </div>
        ))}
      </Panel>

      {/* Recent Projects */}
      <Panel title="Recent Projects (24h)" span={3}>
        {recentProjects.length === 0 ? (
          <div style={{ color: T.textMuted, fontSize: "0.72rem" }}>No project context recorded yet.</div>
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {recentProjects.map((p, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "6px 10px", background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 4,
              }}>
                <div>
                  <span style={{ fontSize: "0.8rem", fontWeight: 600, color: T.gold }}>{p.project}</span>
                  {p.apps && <span style={{ fontSize: "0.65rem", color: T.textMuted, marginLeft: 10 }}>via {p.apps}</span>}
                </div>
                <div style={{ fontSize: "0.65rem", color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
                  {p.entries} check(s)
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function SessionsView({ sessions, accomplishments }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
      {/* Accomplishments */}
      <Panel title="Today's Activity" accent={T.success}>
        {!accomplishments || !accomplishments.ok ? (
          <div style={{ color: T.textMuted, fontSize: "0.72rem" }}>No activity data.</div>
        ) : (
          <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
            <div style={{ color: T.textMuted, marginBottom: 8 }}>{accomplishments.summary}</div>
            {accomplishments.projects?.map((p, i) => (
              <div key={i} style={{ padding: "6px 0", borderBottom: `1px solid ${T.border}` }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: T.gold, fontWeight: 600 }}>{p.project}</span>
                  <span style={{ color: T.textMuted, fontSize: "0.65rem" }}>
                    {p.sessions || p.entries || 0} session(s) · ~{p.minutes || 0}m
                  </span>
                </div>
                {p.apps && (
                  <div style={{ fontSize: "0.65rem", color: T.textMuted, marginTop: 2 }}>
                    via {Array.isArray(p.apps) ? p.apps.join(", ") : p.apps}
                  </div>
                )}
              </div>
            ))}
            {accomplishments.milestones?.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: "0.65rem", color: T.goldDim, textTransform: "uppercase", marginBottom: 4 }}>Milestones</div>
                {accomplishments.milestones.map((m, i) => (
                  <div key={i} style={{ fontSize: "0.72rem", color: T.text, padding: "2px 0" }}>
                    {m.title}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Panel>

      {/* Session Stats */}
      <Panel title="Session Summary" accent={T.info}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "center" }}>
          <Stat label="Sessions" value={accomplishments?.session_count || sessions.length || 0} />
          <Stat label="Projects" value={accomplishments?.projects?.length || 0} color={T.gold} />
          <Stat label="Total Time" value={`${accomplishments?.total_minutes || 0}m`} color={T.success} />
        </div>
      </Panel>

      {/* Session Timeline */}
      <Panel title={`Session History (${sessions.length})`} span={2}>
        {sessions.length === 0 ? (
          <div style={{ color: T.textMuted, fontSize: "0.72rem" }}>
            No sessions recorded yet. Work in VS Code, KiCad, or other engineering tools to build session history.
          </div>
        ) : (
          <div style={{ fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace" }}>
            {sessions.map((s, i) => {
              const apps = Array.isArray(s.apps) ? s.apps : [];
              const files = Array.isArray(s.files) ? s.files : [];
              const started = (s.started_at || "").slice(0, 16).replace("T", " ");
              return (
                <div key={i} style={{ padding: "8px 0", borderBottom: `1px solid ${T.border}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <span style={{ color: T.gold, fontWeight: 600 }}>{s.project}</span>
                      <span style={{ color: T.textMuted, fontSize: "0.65rem", marginLeft: 8 }}>{s.session_type}</span>
                    </div>
                    <div style={{ fontSize: "0.65rem", color: T.textMuted }}>
                      {started} · {s.duration_minutes}m
                    </div>
                  </div>
                  {apps.length > 0 && (
                    <div style={{ fontSize: "0.65rem", color: T.textMuted, marginTop: 2 }}>
                      Apps: {apps.join(", ")}
                    </div>
                  )}
                  {files.length > 0 && (
                    <div style={{ fontSize: "0.65rem", color: T.textMuted }}>
                      Files: {files.join(", ")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}

function OrdersView({ data }) {
  if (!data.orders?.length) {
    return <div style={{ color: T.textMuted, fontSize: "0.8rem", fontFamily: "JetBrains Mono, monospace" }}>{data.summary}</div>;
  }
  return (
    <div>
      <div style={{ fontSize: "0.8rem", color: T.text, marginBottom: 14 }}>{data.summary}</div>
      <div style={{ display: "grid", gap: 6 }}>
        {data.orders.map((o, i) => (
          <div key={i} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "8px 12px", background: T.surface, border: `1px solid ${T.border}`, borderRadius: 4,
          }}>
            <span style={{ fontSize: "0.8rem" }}>{o.part}</span>
            <div style={{ display: "flex", gap: 12, fontSize: "0.7rem" }}>
              <span style={{ color: T.textMuted }}>for {o.project}</span>
              <span style={{
                color: o.priority === "critical" ? T.danger : o.priority === "high" ? T.warning : T.textMuted,
              }}>[{o.priority}]</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
