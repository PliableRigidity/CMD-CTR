import { useEffect, useState, useCallback } from "react";
import { fetchMissions, fetchScheduledTasks, updateScheduledTask, deleteScheduledTask, createScheduledTask, fetchProductivityAuthStatus, fetchCalendarToday, fetchInbox, getGoogleAuthUrl, disconnectGoogle } from "../../lib/api";

const STATUS_CLASS = { active: "active", monitoring: "monitoring", paused: "paused" };
const STATUS_LABEL = { active: "Active", monitoring: "Monitor", paused: "Paused" };

function ScheduledTasksSection() {
  const [tasks, setTasks] = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", prompt: "", interval_minutes: 60 });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchScheduledTasks().then(setTasks).catch(() => {});
    const iv = setInterval(() => {
      fetchScheduledTasks().then(setTasks).catch(() => {});
    }, 60000);
    return () => clearInterval(iv);
  }, []);

  async function toggleEnabled(task) {
    const next = task.enabled ? 0 : 1;
    try {
      const updated = await updateScheduledTask(task.id, { enabled: next });
      setTasks((cur) => cur.map((t) => (t.id === task.id ? updated : t)));
    } catch {}
  }

  async function handleDelete(task) {
    if (!window.confirm(`Delete scheduled task "${task.name}"?`)) return;
    try {
      await deleteScheduledTask(task.id);
      setTasks((cur) => cur.filter((t) => t.id !== task.id));
    } catch {}
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!form.name.trim() || !form.prompt.trim()) return;
    setSubmitting(true);
    try {
      const task = await createScheduledTask({
        name: form.name.trim(),
        prompt: form.prompt.trim(),
        interval_minutes: Number(form.interval_minutes) || 60,
      });
      setTasks((cur) => [...cur, task]);
      setForm({ name: "", prompt: "", interval_minutes: 60 });
      setShowForm(false);
    } catch {} finally {
      setSubmitting(false);
    }
  }

  function fmtInterval(mins) {
    if (mins < 60) return `${mins}min`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m ? `${h}h ${m}min` : `${h}h`;
  }

  function fmtTime(iso) {
    if (!iso) return "never";
    try { return new Date(iso).toLocaleString([], { dateStyle: "short", timeStyle: "short" }); }
    catch { return iso; }
  }

  return (
    <div className="sched-section">
      <div className="sched-header" onClick={() => setCollapsed((v) => !v)} style={{ cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0" }}>
        <span style={{ fontSize: "0.7rem", letterSpacing: "0.08em", opacity: 0.6, textTransform: "uppercase" }}>
          Scheduled Tasks ({tasks.length})
        </span>
        <span style={{ fontSize: "0.65rem", opacity: 0.4 }}>{collapsed ? "▶" : "▼"}</span>
      </div>

      {!collapsed && (
        <>
          <div className="sched-list">
            {tasks.length === 0 && (
              <p className="muted" style={{ fontSize: "0.7rem", padding: "4px 0" }}>
                No scheduled tasks. Create one via chat: "schedule task: check node health every 60 minutes".
              </p>
            )}
            {tasks.map((t) => (
              <div key={t.id} className="sched-task">
                <div className="sched-task-row">
                  <span className={`sched-dot ${t.enabled ? "sched-dot--on" : "sched-dot--off"}`} />
                  <span className="sched-name">{t.name}</span>
                  <span className="sched-interval">{fmtInterval(t.interval_minutes)}</span>
                  <button
                    className="btn-ghost-sm"
                    onClick={() => toggleEnabled(t)}
                    title={t.enabled ? "Pause task" : "Resume task"}
                    style={{ padding: "1px 6px", fontSize: "0.62rem" }}
                  >
                    {t.enabled ? "Pause" : "Resume"}
                  </button>
                  <button
                    className="infra-delete-btn"
                    onClick={() => handleDelete(t)}
                    style={{ padding: "1px 6px", fontSize: "0.62rem" }}
                  >
                    ×
                  </button>
                </div>
                {t.last_run && (
                  <div className="sched-last">
                    <span className="muted" style={{ fontSize: "0.62rem" }}>
                      Last: {fmtTime(t.last_run)}
                    </span>
                    {t.last_result && (
                      <span className="muted" style={{ fontSize: "0.62rem", marginLeft: 6, opacity: 0.5 }}>
                        {t.last_result.slice(0, 60)}{t.last_result.length > 60 ? "…" : ""}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <button
            className="btn-ghost-sm"
            onClick={() => setShowForm((v) => !v)}
            style={{ marginTop: 6, fontSize: "0.65rem" }}
          >
            {showForm ? "Cancel" : "+ New Task"}
          </button>

          {showForm && (
            <form onSubmit={handleCreate} style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
              <input
                className="infra-input"
                placeholder="Task name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
              <input
                className="infra-input"
                placeholder="Prompt (what SILVIA will run)"
                value={form.prompt}
                onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                required
              />
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  className="infra-input"
                  type="number"
                  min={1}
                  placeholder="Interval (minutes)"
                  value={form.interval_minutes}
                  onChange={(e) => setForm((f) => ({ ...f, interval_minutes: e.target.value }))}
                  style={{ width: 110 }}
                />
                <span className="muted" style={{ fontSize: "0.65rem" }}>min</span>
                <button type="submit" className="panel-button" disabled={submitting} style={{ marginLeft: "auto" }}>
                  {submitting ? "Creating…" : "Create"}
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </div>
  );
}

function fmtEventTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch { return iso; }
}

function ProductivitySection() {
  const [auth, setAuth] = useState(null);         // {connected, email} | null
  const [events, setEvents] = useState(null);      // list | null
  const [inbox, setInbox] = useState(null);        // {emails, count} | null
  const [collapsed, setCollapsed] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const status = await fetchProductivityAuthStatus();
      setAuth(status);
      if (status.connected) {
        const [cal, mail] = await Promise.allSettled([fetchCalendarToday(), fetchInbox("is:unread", 5)]);
        if (cal.status === "fulfilled") setEvents(cal.value?.data?.events ?? []);
        if (mail.status === "fulfilled") setInbox(mail.value?.data ?? null);
      }
    } catch {}
  }, []);

  useEffect(() => {
    loadData();
    const iv = setInterval(loadData, 5 * 60 * 1000);
    return () => clearInterval(iv);
  }, [loadData]);

  async function handleConnect() {
    try {
      const resp = await fetch(getGoogleAuthUrl());
      const json = await resp.json();
      if (json.auth_url) window.open(json.auth_url, "_blank", "noopener");
    } catch {}
  }

  async function handleDisconnect() {
    if (!window.confirm("Disconnect Google account?")) return;
    try { await disconnectGoogle(); } catch {}
    setAuth(null); setEvents(null); setInbox(null);
    setTimeout(loadData, 300);
  }

  const unreadCount = inbox?.emails?.filter(e => e.unread)?.length ?? 0;

  return (
    <div className="productivity-section">
      <div
        className="productivity-header"
        onClick={() => setCollapsed(v => !v)}
        style={{ cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0" }}
      >
        <span style={{ fontSize: "0.7rem", letterSpacing: "0.08em", opacity: 0.6, textTransform: "uppercase" }}>
          Productivity
          {auth?.connected && (
            <span style={{ marginLeft: 6, color: "var(--online)", fontSize: "0.6rem" }}>● {auth.email || "connected"}</span>
          )}
        </span>
        <span style={{ fontSize: "0.65rem", opacity: 0.4 }}>{collapsed ? "▶" : "▼"}</span>
      </div>

      {!collapsed && (
        <>
          {!auth?.connected ? (
            <div style={{ padding: "6px 0" }}>
              <p className="muted" style={{ fontSize: "0.7rem", marginBottom: 6 }}>
                Connect Google to see your calendar and email.
              </p>
              <button className="panel-button" style={{ fontSize: "0.65rem" }} onClick={handleConnect}>
                Connect Google
              </button>
            </div>
          ) : (
            <>
              {/* Today's Events */}
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: "0.62rem", opacity: 0.45, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>
                  Today's Events
                </div>
                {events === null ? (
                  <p className="muted" style={{ fontSize: "0.68rem" }}>Loading…</p>
                ) : events.length === 0 ? (
                  <p className="muted" style={{ fontSize: "0.68rem" }}>No events today.</p>
                ) : (
                  events.slice(0, 4).map(ev => (
                    <div key={ev.id} className="prod-event-row">
                      <span className="prod-event-time">{fmtEventTime(ev.start)}</span>
                      <span className="prod-event-title">{ev.title}</span>
                    </div>
                  ))
                )}
              </div>

              {/* Unread Email */}
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: "0.62rem", opacity: 0.45, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>
                  Unread Email {unreadCount > 0 && <span style={{ color: "var(--accent-warm)" }}>({unreadCount})</span>}
                </div>
                {inbox === null ? (
                  <p className="muted" style={{ fontSize: "0.68rem" }}>Loading…</p>
                ) : (inbox.emails || []).filter(e => e.unread).slice(0, 3).length === 0 ? (
                  <p className="muted" style={{ fontSize: "0.68rem" }}>Inbox clear.</p>
                ) : (
                  (inbox.emails || []).filter(e => e.unread).slice(0, 3).map(e => (
                    <div key={e.id} className="prod-email-row">
                      <span className="prod-email-subject">{e.subject}</span>
                      <span className="prod-email-from muted">{e.sender?.split("<")[0]?.trim()?.slice(0, 20)}</span>
                    </div>
                  ))
                )}
              </div>

              <button
                className="btn-ghost-sm"
                onClick={handleDisconnect}
                style={{ fontSize: "0.58rem", opacity: 0.4, marginTop: 2 }}
              >
                Disconnect Google
              </button>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default function MissionPanel({ mode, onOpenIntel }) {
  const [missions, setMissions] = useState([]);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    fetchMissions()
      .then(setMissions)
      .catch(() => {});
  }, []);

  return (
    <section className="panel mission-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Mission Layer / Ops Context</p>
          <h2>Active Missions</h2>
        </div>
        <span
          className={`state-pill state-pill--${mode === "decision" ? "busy" : "idle"}`}
          style={{ fontSize: "0.6rem", padding: "2px 8px" }}
        >
          {mode === "decision" ? "Council" : "Direct"}
        </span>
      </div>

      <div className="mission-strip">
        {missions.map((m) => (
          <div key={m.id}>
            <button
              type="button"
              className="mission-row"
              onClick={() => setExpanded(expanded === m.id ? null : m.id)}
            >
              <span className={`mission-dot mission-dot--${STATUS_CLASS[m.status] ?? "active"}`} />
              <span className="mission-code">{m.code}</span>
              <span className="mission-name">{m.name}</span>
              <span className="mission-status">{STATUS_LABEL[m.status] ?? m.status}</span>
            </button>
            {expanded === m.id && (
              <p className="mission-desc">{m.description}</p>
            )}
          </div>
        ))}
      </div>

      <ScheduledTasksSection />
      <ProductivitySection />

      <button type="button" className="panel-button intel-link-btn" onClick={onOpenIntel}>
        Intel Board →
      </button>
    </section>
  );
}
