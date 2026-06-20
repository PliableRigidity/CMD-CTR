import { useEffect, useState } from "react";
import { fetchProjects, updateProject, createProject, deleteProject, fetchProjectHealth, fetchProjectBriefing, fetchBlockedProjects, fetchStartableProjects } from "../../lib/api";

const STATUS_ICON = { active: "◉", paused: "◎", complete: "✓", blocked: "✗" };
const STATUS_CLASS = { active: "active", paused: "monitoring", complete: "ok", blocked: "danger" };
const PRI_BADGE = { critical: "crit", high: "high", normal: null, low: "low" };

const EMPTY_FORM = { name: "", status: "active", priority: "normal", brain63_key: "", notes: "" };

function PriorityBadge({ priority }) {
  const badge = PRI_BADGE[priority];
  if (!badge) return null;
  return <span className={`proj-pri proj-pri--${badge}`}>{priority}</span>;
}

function ProjectRow({ project, onStatusChange, onDelete, onSelect, selected }) {
  const icon = STATUS_ICON[project.status] || "·";
  const cls = STATUS_CLASS[project.status] || "";
  return (
    <div
      className={`proj-row${selected ? " proj-row--selected" : ""}`}
      onClick={() => onSelect(selected ? null : project.id)}
    >
      <span className={`proj-icon status-dot status-dot--${cls}`}>{icon}</span>
      <span className="proj-name">{project.name}</span>
      <PriorityBadge priority={project.priority} />
      {project.brain63_key && (
        <span className="proj-b63" title={`Brain63: ${project.brain63_key}`}>B63</span>
      )}
    </div>
  );
}

function ProjectIntelligenceSection({ projectName }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setData(null);
    fetchProjectBriefing(projectName)
      .then((r) => { if (active) setData(r.data); })
      .catch(() => {})
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectName]);

  if (loading) return <div className="pi-loading">Loading intelligence…</div>;
  if (!data || !data.found) return null;

  const pct = data.readiness_pct || 0;
  const fill = Math.round(pct / 10);
  const missing = data.parts?.missing || [];
  const blockers = data.blockers || [];
  const tasks = data.tasks || {};
  const action = data.recommended_action || "";
  const b63 = data.brain63_context;

  return (
    <div className="pi-section">
      <div className="pi-header">Intelligence</div>

      <div className="pi-readiness-row">
        <span className="pi-label">Readiness</span>
        <div className="pi-bar-track">
          {Array.from({ length: 10 }).map((_, i) => (
            <span key={i} className={`pi-seg${i < fill ? " pi-seg--fill" : ""}`} />
          ))}
        </div>
        <span className="pi-pct">{pct}%</span>
      </div>

      {missing.length > 0 && (
        <div className="pi-row">
          <span className="pi-label pi-label--danger">Missing</span>
          <span className="pi-val">{missing.slice(0, 3).map((p) => p.name).join(", ")}{missing.length > 3 ? ` +${missing.length - 3}` : ""}</span>
        </div>
      )}

      {blockers.length > 0 && (
        <div className="pi-row">
          <span className="pi-label pi-label--danger">Blockers</span>
          <span className="pi-val pi-val--danger">{blockers.length}</span>
        </div>
      )}

      {tasks.open > 0 && (
        <div className="pi-row">
          <span className="pi-label">Tasks</span>
          <span className="pi-val">{tasks.open} open</span>
        </div>
      )}

      {b63 && (
        <div className="pi-b63">{b63.slice(0, 140)}{b63.length > 140 ? "…" : ""}</div>
      )}

      {action && <div className="pi-action">→ {action}</div>}
    </div>
  );
}

function ProjectDetail({ project, healthData, onStatusChange, onDelete, onClose }) {
  const health = healthData?.find((h) => h.id === project.id);
  const _HEALTH_COLOR = { healthy: "var(--clr-ok, #22c55e)", stale: "var(--clr-warn, #f59e0b)", blocked: "var(--clr-danger, #ef4444)", "no activity": "var(--clr-muted, #6b7280)" };
  return (
    <div className="proj-detail">
      <div className="proj-detail-header">
        <span className="proj-detail-name">{project.name}</span>
        <button className="proj-close" onClick={onClose} title="Close">✕</button>
      </div>
      {project.notes && <p className="proj-notes">{project.notes}</p>}
      <div className="proj-meta-row">
        <span className="proj-meta-label">Status</span>
        <select
          className="proj-select"
          value={project.status}
          onChange={(e) => onStatusChange(project.id, e.target.value)}
        >
          {["active", "paused", "blocked", "complete"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span className="proj-meta-label" style={{ marginLeft: 8 }}>Priority</span>
        <select
          className="proj-select"
          value={project.priority}
          onChange={(e) => onStatusChange(project.id, null, e.target.value)}
        >
          {["critical", "high", "normal", "low"].map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>
      {project.brain63_key && (
        <div className="proj-meta-row">
          <span className="proj-meta-label">Brain63</span>
          <span className="proj-meta-val muted">{project.brain63_key}</span>
        </div>
      )}
      {health && (
        <div className="proj-health-block">
          <span className="proj-meta-label">Health</span>
          <span style={{ color: _HEALTH_COLOR[health.health] || "inherit", fontSize: "0.7rem", marginLeft: 6 }}>
            {health.health}
          </span>
          <span className="muted" style={{ fontSize: "0.65rem", marginLeft: 8 }}>{health.last_activity}</span>
          {health.pending_tasks > 0 && (
            <span className="proj-task-count">{health.pending_tasks} task{health.pending_tasks !== 1 ? "s" : ""}</span>
          )}
          {health.task_titles?.length > 0 && (
            <ul className="proj-task-list">
              {health.task_titles.map((t, i) => <li key={i}>{t}</li>)}
            </ul>
          )}
        </div>
      )}
      <ProjectIntelligenceSection projectName={project.name} />
      <button className="proj-delete-btn" onClick={() => onDelete(project)}>Remove project</button>
    </div>
  );
}

export default function ProjectsPanel() {
  const [projects, setProjects] = useState([]);
  const [health, setHealth] = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [tab, setTab] = useState("active"); // active | all
  const [piFilter, setPiFilter] = useState(null); // null | "blocked" | "startable"
  const [piData, setPiData] = useState([]);

  useEffect(() => {
    load();
    const iv = setInterval(load, 60000);
    return () => clearInterval(iv);
  }, []);

  function load() {
    fetchProjects().then(setProjects).catch(() => {});
    fetchProjectHealth().then(setHealth).catch(() => {});
  }

  async function handleStatusChange(id, status, priority) {
    try {
      const patch = {};
      if (status) patch.status = status;
      if (priority) patch.priority = priority;
      const updated = await updateProject(id, patch);
      setProjects((cur) => cur.map((p) => (p.id === id ? updated : p)));
    } catch {}
  }

  async function handleDelete(project) {
    if (!window.confirm(`Remove project "${project.name}"?`)) return;
    try {
      await deleteProject(project.id);
      setProjects((cur) => cur.filter((p) => p.id !== project.id));
      if (selectedId === project.id) setSelectedId(null);
    } catch {}
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSubmitting(true);
    try {
      const created = await createProject({
        name: form.name.trim(),
        status: form.status,
        priority: form.priority,
        brain63_key: form.brain63_key.trim() || null,
        notes: form.notes.trim() || null,
      });
      setProjects((cur) => [...cur, created]);
      setForm(EMPTY_FORM);
      setShowForm(false);
    } catch {} finally {
      setSubmitting(false);
    }
  }

  const visible = tab === "active"
    ? projects.filter((p) => p.status === "active" || p.status === "blocked")
    : projects;

  const selected = projects.find((p) => p.id === selectedId) || null;
  const activeCount = projects.filter((p) => p.status === "active").length;

  return (
    <section className="mission-section proj-panel">
      <div
        className="mission-section__header"
        onClick={() => setCollapsed((v) => !v)}
        style={{ cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span className="mission-section__label">
          Projects
          <span className="mission-section__count"> ({activeCount} active)</span>
        </span>
        <span style={{ fontSize: "0.6rem", opacity: 0.4 }}>{collapsed ? "▶" : "▼"}</span>
      </div>

      {!collapsed && (
        <>
          <div className="proj-tabs">
            <button
              className={`proj-tab${tab === "active" ? " proj-tab--active" : ""}`}
              onClick={() => { setTab("active"); setPiFilter(null); }}
            >Active</button>
            <button
              className={`proj-tab${tab === "all" ? " proj-tab--active" : ""}`}
              onClick={() => { setTab("all"); setPiFilter(null); }}
            >All</button>
            <button
              className="proj-add-btn"
              onClick={() => setShowForm((v) => !v)}
              title="New project"
            >+</button>
          </div>
          <div className="pi-filter-bar">
            <button
              className={`pi-filter-btn${piFilter === "blocked" ? " pi-filter-btn--active" : ""}`}
              onClick={() => {
                if (piFilter === "blocked") { setPiFilter(null); return; }
                setPiFilter("blocked");
                fetchBlockedProjects().then((r) => setPiData(r.data || [])).catch(() => setPiData([]));
              }}
            >✗ Blocked</button>
            <button
              className={`pi-filter-btn${piFilter === "startable" ? " pi-filter-btn--active" : ""}`}
              onClick={() => {
                if (piFilter === "startable") { setPiFilter(null); return; }
                setPiFilter("startable");
                fetchStartableProjects().then((r) => setPiData(r.data || [])).catch(() => setPiData([]));
              }}
            >● Ready</button>
          </div>
          {piFilter && piData.length > 0 && (
            <div className="pi-quick-list">
              {piData.map((p, i) => (
                <div key={i} className="pi-quick-row">
                  <span className={`pi-quick-icon${piFilter === "blocked" ? " pi-quick-icon--danger" : " pi-quick-icon--ok"}`}>
                    {piFilter === "blocked" ? "✗" : "●"}
                  </span>
                  <span className="pi-quick-name">{p.name}</span>
                  {p.readiness_pct != null && <span className="pi-quick-pct">{p.readiness_pct}%</span>}
                  {p.blocking_parts?.length > 0 && (
                    <span className="pi-quick-reason">{p.blocking_parts.slice(0,2).join(", ")}</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {piFilter && piData.length === 0 && (
            <p className="muted" style={{ fontSize: "0.65rem", padding: "4px 6px" }}>
              No {piFilter} projects found.
            </p>
          )}

          {showForm && (
            <form className="proj-form" onSubmit={handleCreate}>
              <input
                className="proj-input"
                placeholder="Project name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
              <div className="proj-form-row">
                <select
                  className="proj-select"
                  value={form.status}
                  onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
                >
                  {["active", "paused", "blocked"].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <select
                  className="proj-select"
                  value={form.priority}
                  onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
                >
                  {["critical", "high", "normal", "low"].map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <input
                className="proj-input"
                placeholder="Brain63 key (optional)"
                value={form.brain63_key}
                onChange={(e) => setForm((f) => ({ ...f, brain63_key: e.target.value }))}
              />
              <textarea
                className="proj-input"
                placeholder="Notes (optional)"
                rows={2}
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
              <div style={{ display: "flex", gap: 6 }}>
                <button type="submit" className="proj-btn proj-btn--primary" disabled={submitting}>
                  {submitting ? "Creating..." : "Create"}
                </button>
                <button type="button" className="proj-btn" onClick={() => setShowForm(false)}>Cancel</button>
              </div>
            </form>
          )}

          <div className="proj-list">
            {visible.length === 0 && (
              <p className="muted" style={{ fontSize: "0.65rem", padding: "4px 0" }}>
                No {tab === "active" ? "active " : ""}projects.
              </p>
            )}
            {visible.map((p) => (
              <ProjectRow
                key={p.id}
                project={p}
                selected={selectedId === p.id}
                onSelect={setSelectedId}
                onStatusChange={handleStatusChange}
                onDelete={handleDelete}
              />
            ))}
          </div>

          {selected && (
            <ProjectDetail
              project={selected}
              healthData={health}
              onStatusChange={handleStatusChange}
              onDelete={handleDelete}
              onClose={() => setSelectedId(null)}
            />
          )}
        </>
      )}
    </section>
  );
}
