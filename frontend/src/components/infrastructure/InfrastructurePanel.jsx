import { useMemo, useState, useEffect, useCallback } from "react";
import TelemetryChart from "./TelemetryChart";
import { executeCapabilityUI, fetchFleetStatus, fetchRecentActions } from "../../lib/api";

const SOURCE_LABELS = {
  tailscale: "Tailscale",
  dns: "DNS",
  registry: "Registry",
};

function getIpInfo(node) {
  if (node.tailscale_ip) return { ip: node.tailscale_ip, source: "tailscale" };
  if (node.resolved_ip) return { ip: node.resolved_ip, source: "dns" };
  const hostname = node.hostname || "";
  if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname)) return { ip: hostname, source: "registry" };
  return { ip: null, source: "unknown" };
}

const NODE_TYPES = [
  "workstation", "server", "raspberry-pi", "vps", "nas",
  "router", "vm", "container", "cyberdeck", "edge-device",
  "drone", "robot", "esp32", "sensor-network", "custom",
];

const STATUS_DOT = {
  online: "online",
  offline: "offline",
  standby: "standby",
  unknown: "unknown",
};

const EMPTY_FORM = {
  name: "",
  type: "custom",
  hostname: "",
  tailscale_name: "",
  agent_url: "",
  tags: "",
  notes: "",
};

function MetricBar({ value, label }) {
  if (value == null) return null;
  const pct = Math.min(100, Math.max(0, value));
  const cls = pct > 90 ? "danger" : pct > 75 ? "warn" : "ok";
  return (
    <span className={`infra-metric infra-metric--${cls}`} title={`${label}: ${pct.toFixed(0)}%`}>
      {label} {pct.toFixed(0)}%
    </span>
  );
}

const VERIFY_SOURCE_LABELS = {
  local: "Local",
  "silvia-agent": "Silvia-Agent",
  tailscale: "Tailscale",
  dns: "DNS",
  ping: "Ping",
};

const SVC_STATUS_ICON = { running: "●", stopped: "○", failed: "✗", unknown: "?" };
const SVC_STATUS_CLASS = { running: "svc-running", stopped: "svc-stopped", failed: "svc-failed", unknown: "svc-unknown" };

function NodeServicesSection({ nodeId, legacyServices, legacyCapabilities }) {
  const [services, setServices] = useState(null);
  const [open, setOpen] = useState(false);
  const [execResults, setExecResults] = useState({});  // key: `${svcId}:${capName}` → {ok, summary}
  const [executing, setExecuting] = useState(null);    // key of the in-flight execution

  const fetchServices = useCallback(() => {
    fetch(`/api/services?node_id=${encodeURIComponent(nodeId)}`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setServices)
      .catch(() => setServices([]));
  }, [nodeId]);

  useEffect(() => {
    if (!open) return;
    fetchServices();
  }, [open, fetchServices]);

  useEffect(() => {
    function onServicesChanged() { if (open) fetchServices(); }
    window.addEventListener("silvia:services_changed", onServicesChanged);
    return () => window.removeEventListener("silvia:services_changed", onServicesChanged);
  }, [open, fetchServices]);

  async function handleExecute(svc, cap) {
    const key = `${svc.id}:${cap.name}`;
    setExecuting(key);
    const result = await executeCapabilityUI(cap.name, svc.id, {});
    setExecResults((prev) => ({ ...prev, [key]: result }));
    setExecuting(null);
    setTimeout(() => setExecResults((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    }), 5000);
  }

  const hasStructured = services && services.length > 0;
  const hasLegacy = (legacyServices && legacyServices.length > 0) || (legacyCapabilities && legacyCapabilities.length > 0);

  if (!hasLegacy && !open && !hasStructured) return null;

  return (
    <>
      {hasStructured ? (
        <div className="infra-detail-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="infra-detail-label">Services</span>
            <button className="infra-action-btn" style={{ fontSize: "0.6rem", padding: "1px 6px" }}
              onClick={() => setOpen(!open)}>
              {open ? "hide" : `${services.length}`}
            </button>
          </div>
          {open && services.map((svc) => (
            <div key={svc.id} className="svc-row">
              <span className={`svc-status-dot ${SVC_STATUS_CLASS[svc.status] || "svc-unknown"}`}>
                {SVC_STATUS_ICON[svc.status] || "?"}
              </span>
              <span className="svc-name">{svc.name}</span>
              <span className="svc-transport">[{svc.transport}]</span>
              <span className={`svc-status-label ${SVC_STATUS_CLASS[svc.status] || "svc-unknown"}`}>{svc.status}</span>
              {svc.capabilities && svc.capabilities.length > 0 && (
                <div className="svc-caps">
                  {svc.capabilities.map((cap) => {
                    const key = `${svc.id}:${cap.name}`;
                    const res = execResults[key];
                    const busy = executing === key;
                    return (
                      <span key={cap.id || cap.name} className="svc-cap-item">
                        <span className="infra-tag svc-cap-tag">{cap.name || cap}</span>
                        {cap.id && (
                          <button
                            className={`cap-execute-btn${busy ? " cap-execute-btn--busy" : ""}`}
                            disabled={busy || !!executing}
                            onClick={() => handleExecute(svc, cap)}
                            title={`Execute ${cap.name} on ${svc.name}`}
                          >
                            {busy ? "…" : "▶"}
                          </button>
                        )}
                        {res && (
                          <span className={res.ok ? "cap-result-ok" : "cap-result-err"}>
                            {res.ok ? "✓" : "✗"} {res.summary}
                          </span>
                        )}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : hasLegacy ? (
        <>
          {legacyServices && legacyServices.length > 0 && (
            <div className="infra-detail-row">
              <span className="infra-detail-label">Services</span>
              <span>
                {legacyServices.map((s) => <span key={s} className="infra-tag">{s}</span>)}
              </span>
              <button className="infra-action-btn" style={{ fontSize: "0.6rem", padding: "1px 6px", marginLeft: 4 }}
                onClick={() => setOpen(!open)}>
                {open ? "hide" : "structured"}
              </button>
            </div>
          )}
          {legacyCapabilities && legacyCapabilities.length > 0 && (
            <div className="infra-detail-row">
              <span className="infra-detail-label">Capabilities</span>
              <span className="muted" style={{ fontSize: "0.7rem" }}>
                {legacyCapabilities.join(", ")}
              </span>
            </div>
          )}
          {open && services !== null && services.length === 0 && (
            <div className="infra-detail-row">
              <span className="muted" style={{ fontSize: "0.7rem" }}>No structured services registered.</span>
            </div>
          )}
        </>
      ) : (
        <div className="infra-detail-row">
          <span className="infra-detail-label">Services</span>
          <button className="infra-action-btn" style={{ fontSize: "0.6rem", padding: "1px 6px" }}
            onClick={() => setOpen(!open)}>
            {open ? "hide" : "load"}
          </button>
          {open && services !== null && (
            <span className="muted" style={{ fontSize: "0.7rem", marginLeft: 8 }}>
              {services.length === 0 ? "No services registered." : `${services.length} service(s) loaded.`}
            </span>
          )}
        </div>
      )}
    </>
  );
}

function FleetDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const r = await fetchFleetStatus();
        if (active) setData(r.data);
      } catch {
        if (active) setError("unavailable");
      }
    }
    load();
    const id = setInterval(load, 30000);
    return () => { active = false; clearInterval(id); };
  }, []);

  if (error) return null;
  if (!data) return <div className="fleet-loading">Fleet…</div>;

  const { health_score: score, total, online, offline, warning, critical, healthy, active_alerts: alerts } = data;
  const fill = Math.round((score / 100) * 10);
  const grade = score >= 90 ? "A" : score >= 75 ? "B" : score >= 60 ? "C" : score >= 40 ? "D" : "F";
  const gradeClass = score >= 90 ? "fleet-grade--a" : score >= 75 ? "fleet-grade--b" : score >= 60 ? "fleet-grade--c" : "fleet-grade--d";

  return (
    <div className="fleet-bar">
      <div className="fleet-score-wrap">
        <span className="fleet-label">Fleet</span>
        <span className={`fleet-grade ${gradeClass}`}>{grade}</span>
        <div className="fleet-bar-track">
          {Array.from({ length: 10 }).map((_, i) => (
            <span key={i} className={`fleet-seg ${i < fill ? "fleet-seg--fill" : ""}`} />
          ))}
        </div>
        <span className="fleet-score">{score}</span>
      </div>
      <div className="fleet-stats">
        <span className="fleet-stat fleet-stat--online">● {online}/{total}</span>
        {offline > 0 && <span className="fleet-stat fleet-stat--offline">✕ {offline} offline</span>}
        {(warning + critical) > 0 && (
          <span className="fleet-stat fleet-stat--warn">▲ {warning + critical} degraded</span>
        )}
        {alerts > 0 && <span className="fleet-stat fleet-stat--alert">{alerts} alert{alerts !== 1 ? "s" : ""}</span>}
        {offline === 0 && (warning + critical) === 0 && alerts === 0 && (
          <span className="fleet-stat fleet-stat--healthy">{healthy} healthy</span>
        )}
      </div>
    </div>
  );
}

function RecentActivity() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const r = await fetchRecentActions(10);
        if (active) setRows(r.data || []);
      } catch {
        if (active) setError("unavailable");
      }
    }
    load();
    const id = setInterval(load, 15000);
    return () => { active = false; clearInterval(id); };
  }, []);

  if (error || rows.length === 0) return null;

  const STATUS_ICON = { success: "●", failure: "✕", simulated: "◎", dry_run: "◌", partial: "▲" };
  const STATUS_CLASS = { success: "obs-success", failure: "obs-failure", simulated: "obs-sim", dry_run: "obs-dry", partial: "obs-partial" };

  return (
    <div className="obs-panel">
      <div className="obs-header">Recent Activity</div>
      <ul className="obs-list">
        {rows.map((r, i) => {
          const icon  = STATUS_ICON[r.status] || "○";
          const cls   = STATUS_CLASS[r.status] || "";
          const cap   = r.capability || r.tool || "?";
          const node  = r.node || "local";
          const ts    = (r.ts || "").slice(11, 16);
          const msg   = r.message ? ` — ${r.message.slice(0, 48)}` : "";
          return (
            <li key={i} className={`obs-row ${cls}`}>
              <span className="obs-icon">{icon}</span>
              <span className="obs-cap">{cap}</span>
              <span className="obs-node">{node}</span>
              <span className="obs-msg">{msg}</span>
              <span className="obs-ts">{ts}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function InfrastructurePanel({ nodes = [], liveTelemetryPoints = {}, onAddNode, onSaveNode, onProbeNode, onVerifyNode, onDeleteNode }) {
  const [expanded, setExpanded] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(EMPTY_FORM);
  const [configuringId, setConfiguringId] = useState(null);
  const [configForm, setConfigForm] = useState({ agent_url: "", notes: "", tags: "" });
  const [submitting, setSubmitting] = useState(false);
  const [probingId, setProbingId] = useState(null);
  const [verifyingId, setVerifyingId] = useState(null);

  const onlineCount = nodes.filter((n) => n.status === "online").length;
  const filteredNodes = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return nodes;
    return nodes.filter((node) => {
      const haystack = [
        node.name,
        node.type,
        node.hostname,
        node.tailscale_name,
        node.tailscale_ip,
        node.notes,
        ...(node.tags || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [nodes, query]);

  function toggleExpand(id) {
    setExpanded((cur) => (cur === id ? null : id));
  }

  async function handleAdd(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSubmitting(true);
    try {
      await onAddNode({
        name: form.name.trim(),
        type: form.type,
        hostname: form.hostname.trim(),
        tailscale_name: form.tailscale_name.trim() || undefined,
        agent_url: form.agent_url.trim() || undefined,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        notes: form.notes.trim() || undefined,
      });
      setForm(EMPTY_FORM);
      setShowForm(false);
    } finally {
      setSubmitting(false);
    }
  }

  function startEdit(node) {
    setEditingId(node.id);
    setEditForm({
      name: node.name || "",
      type: node.type || "custom",
      hostname: node.hostname || "",
      tailscale_name: node.tailscale_name || "",
      agent_url: node.agent_url || "",
      tags: (node.tags || []).join(", "),
      notes: node.notes || "",
    });
  }

  async function handleSaveEdit(e) {
    e.preventDefault();
    if (!editingId || !onSaveNode || !editForm.name.trim()) return;
    setSubmitting(true);
    try {
      await onSaveNode(editingId, {
        name: editForm.name.trim(),
        type: editForm.type,
        hostname: editForm.hostname.trim(),
        tailscale_name: editForm.tailscale_name.trim() || null,
        agent_url: editForm.agent_url.trim() || null,
        tags: editForm.tags.split(",").map((t) => t.trim()).filter(Boolean),
        notes: editForm.notes.trim() || null,
      });
      setEditingId(null);
    } finally {
      setSubmitting(false);
    }
  }

  function startConfigure(node) {
    setConfiguringId(node.id);
    setConfigForm({
      agent_url: node.agent_url || "",
      notes: node.notes || "",
      tags: (node.tags || []).join(", "),
    });
  }

  async function handleSaveConfigure(e) {
    e.preventDefault();
    if (!configuringId || !onSaveNode) return;
    setSubmitting(true);
    try {
      await onSaveNode(configuringId, {
        agent_url: configForm.agent_url.trim() || null,
        notes: configForm.notes.trim() || null,
        tags: configForm.tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setConfiguringId(null);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("Remove this node from the registry?")) return;
    await onDeleteNode(id);
    if (expanded === id) setExpanded(null);
    if (editingId === id) setEditingId(null);
  }

  async function handleProbe(id) {
    if (!onProbeNode) return;
    setProbingId(id);
    try {
      await onProbeNode(id);
    } finally {
      setProbingId(null);
    }
  }

  async function handleVerify(id) {
    if (!onVerifyNode) return;
    setVerifyingId(id);
    try {
      await onVerifyNode(id);
    } finally {
      setVerifyingId(null);
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading" style={{ marginBottom: "10px" }}>
        <div>
          <p className="eyebrow">Node Registry</p>
          <h2>Infrastructure</h2>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span className="muted" style={{ fontSize: "0.68rem" }}>
            {onlineCount}/{nodes.length} online
          </span>
          <button
            className="btn-ghost-sm"
            onClick={() => setShowForm((v) => !v)}
          >
            {showForm ? "Cancel" : "+ Add"}
          </button>
        </div>
      </div>

      <FleetDashboard />
      <RecentActivity />

      <input
        className="infra-input"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search nodes, tags, hostnames, or Tailscale names"
        style={{ marginBottom: "10px" }}
      />

      <div className="infra-list">
        {filteredNodes.map((node) => (
          <div key={node.id} className="infra-node">
            <button
              className={`infra-row ${expanded === node.id ? "infra-row--expanded" : ""}`}
              onClick={() => toggleExpand(node.id)}
            >
              <span className={`infra-dot infra-dot--${STATUS_DOT[node.status] || "unknown"}`} />
              <span className="infra-name">{node.name}</span>
              {node.id === "workstation" && (
                <span className="infra-system-badge" title="Managed by CMD-CTR — core system node">SYSTEM</span>
              )}
              {node.agent_url && (
                <span className="infra-agent-badge" title={node.agent_url}>AGENT</span>
              )}
              <span className="infra-metrics-inline">
                <MetricBar value={node.cpu} label="CPU" />
                <MetricBar value={node.ram} label="RAM" />
              </span>
              <span className={`infra-status infra-status--${STATUS_DOT[node.status] || "unknown"}`}>
                {node.status.toUpperCase()}
              </span>
            </button>

            {expanded === node.id && (
              <div className="infra-detail">
                {editingId === node.id ? (
                  <form className="infra-add-form" onSubmit={handleSaveEdit} style={{ marginBottom: "10px" }}>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={editForm.name}
                        onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                        placeholder="Node name *"
                        required
                      />
                      <select
                        className="infra-input"
                        value={editForm.type}
                        onChange={(e) => setEditForm((f) => ({ ...f, type: e.target.value }))}
                      >
                        {NODE_TYPES.map((t) => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                    </div>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={editForm.hostname}
                        onChange={(e) => setEditForm((f) => ({ ...f, hostname: e.target.value }))}
                        placeholder="Hostname / IP"
                      />
                      <input
                        className="infra-input"
                        value={editForm.tailscale_name}
                        onChange={(e) => setEditForm((f) => ({ ...f, tailscale_name: e.target.value }))}
                        placeholder="Tailscale name"
                      />
                    </div>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={editForm.agent_url}
                        onChange={(e) => setEditForm((f) => ({ ...f, agent_url: e.target.value }))}
                        placeholder="Agent URL (e.g. http://100.64.1.5:8765)"
                      />
                    </div>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={editForm.tags}
                        onChange={(e) => setEditForm((f) => ({ ...f, tags: e.target.value }))}
                        placeholder="Tags (comma-separated)"
                      />
                    </div>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={editForm.notes}
                        onChange={(e) => setEditForm((f) => ({ ...f, notes: e.target.value }))}
                        placeholder="Notes"
                      />
                    </div>
                    <div className="button-row">
                      <button type="submit" className="panel-button" disabled={submitting}>
                        {submitting ? "Saving..." : "Save"}
                      </button>
                      <button type="button" className="btn-ghost-sm" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : null}

                <div className="infra-detail-row">
                  <span className="infra-detail-label">Type</span>
                  <span>{node.type}</span>
                </div>
                <div className="infra-detail-row">
                  <span className="infra-detail-label">Verified</span>
                  {node.last_verified ? (
                    <span>
                      <span className="infra-verified-badge">
                        {VERIFY_SOURCE_LABELS[node.verification_source] || node.verification_source || "unknown"}
                      </span>
                      <span className="muted" style={{ fontSize: "0.68rem", marginLeft: "6px" }}>
                        {new Date(node.last_verified).toLocaleString()}
                      </span>
                    </span>
                  ) : (
                    <span className="muted" style={{ fontSize: "0.68rem" }}>Not yet verified</span>
                  )}
                </div>
                {node.hostname && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Host</span>
                    <span>{node.hostname}</span>
                  </div>
                )}
                {node.tailscale_name && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Tailscale</span>
                    <span>{node.tailscale_name}</span>
                  </div>
                )}
                {(() => {
                  const { ip, source } = getIpInfo(node);
                  return (
                    <div className="infra-detail-row">
                      <span className="infra-detail-label">IP</span>
                      {ip ? (
                        <span>
                          <span className="mono">{ip}</span>
                          <span className="infra-source-badge">{SOURCE_LABELS[source] || "unknown"}</span>
                        </span>
                      ) : (
                        <span className="muted">unknown</span>
                      )}
                    </div>
                  );
                })()}
                <div className="infra-detail-row">
                  <span className="infra-detail-label">Metrics</span>
                  <span>
                    {[
                      node.cpu != null && `CPU ${node.cpu.toFixed(0)}%`,
                      node.ram != null && `RAM ${node.ram.toFixed(0)}%`,
                      node.disk != null && `Disk ${node.disk.toFixed(0)}%`,
                      node.temperature != null && `${node.temperature.toFixed(0)}°C`,
                      node.uptime != null && `Up ${Math.floor(node.uptime / 3600)}h`,
                    ].filter(Boolean).join(" · ") || "—"}
                  </span>
                </div>
                <NodeServicesSection nodeId={node.id} legacyServices={node.services} legacyCapabilities={node.capabilities} />
                {node.agent_url && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Agent</span>
                    <span className="mono" style={{ fontSize: "0.7rem" }}>{node.agent_url}</span>
                  </div>
                )}
                {node.last_seen && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Last seen</span>
                    <span className="muted" style={{ fontSize: "0.7rem" }}>
                      {new Date(node.last_seen).toLocaleString()}
                    </span>
                  </div>
                )}
                {node.last_probe_at && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Last probe</span>
                    <span className="muted" style={{ fontSize: "0.7rem" }}>
                      {new Date(node.last_probe_at).toLocaleString()}
                    </span>
                  </div>
                )}
                {(node.hostname_valid != null || node.resolved_ip || node.latency_ms != null || node.tailscale_reachable != null) && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Connectivity</span>
                    <span>
                      {[
                        node.hostname_valid != null && `Hostname ${node.hostname_valid ? "valid" : "invalid"}`,
                        node.resolved_ip && `Resolved ${node.resolved_ip}`,
                        node.latency_ms != null && `Latency ${node.latency_ms.toFixed(0)}ms`,
                        node.tailscale_reachable != null && `Tailscale ${node.tailscale_reachable ? "reachable" : "unreachable"}`,
                      ].filter(Boolean).join(" · ") || "—"}
                    </span>
                  </div>
                )}
                {node.probe_error && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Probe detail</span>
                    <span className="muted" style={{ fontSize: "0.7rem" }}>{node.probe_error}</span>
                  </div>
                )}
                {node.tags.length > 0 && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Tags</span>
                    <span>
                      {node.tags.map((t) => (
                        <span key={t} className="infra-tag">{t}</span>
                      ))}
                    </span>
                  </div>
                )}
                {node.notes && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Notes</span>
                    <span className="muted" style={{ fontSize: "0.7rem" }}>{node.notes}</span>
                  </div>
                )}

                {/* Telemetry history chart — shown when node has metrics data */}
                {(node.cpu != null || node.ram != null || node.battery_pct != null) && (
                  <div style={{ paddingTop: 4, paddingBottom: 4 }}>
                    <p className="infra-detail-label" style={{ marginBottom: 2 }}>History (6h)</p>
                    <TelemetryChart
                      nodeId={node.id}
                      isRobotics={["drone","robot","esp32","sensor-network"].includes(node.type)}
                      livePoint={liveTelemetryPoints[node.id] || null}
                    />
                  </div>
                )}

                {/* System node configure form */}
                {node.id === "workstation" && configuringId === node.id && (
                  <form className="infra-add-form" onSubmit={handleSaveConfigure} style={{ marginTop: "8px" }}>
                    <p className="infra-system-note">System node — only agent URL, tags, and notes can be changed.</p>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={configForm.agent_url}
                        onChange={(e) => setConfigForm((f) => ({ ...f, agent_url: e.target.value }))}
                        placeholder="Agent URL (e.g. http://127.0.0.1:8765)"
                      />
                    </div>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={configForm.tags}
                        onChange={(e) => setConfigForm((f) => ({ ...f, tags: e.target.value }))}
                        placeholder="Tags (comma-separated)"
                      />
                    </div>
                    <div className="infra-form-row">
                      <input
                        className="infra-input"
                        value={configForm.notes}
                        onChange={(e) => setConfigForm((f) => ({ ...f, notes: e.target.value }))}
                        placeholder="Notes"
                      />
                    </div>
                    <div className="button-row">
                      <button type="submit" className="panel-button" disabled={submitting}>
                        {submitting ? "Saving..." : "Save"}
                      </button>
                      <button type="button" className="btn-ghost-sm" onClick={() => setConfiguringId(null)}>
                        Cancel
                      </button>
                    </div>
                  </form>
                )}

                <div className="button-row">
                  <button className="btn-ghost-sm" onClick={() => handleProbe(node.id)} disabled={probingId === node.id}>
                    {probingId === node.id ? "Probing..." : "Probe"}
                  </button>
                  <button className="btn-ghost-sm" onClick={() => handleVerify(node.id)} disabled={verifyingId === node.id}>
                    {verifyingId === node.id ? "Verifying..." : "Verify"}
                  </button>
                  {node.id === "workstation" ? (
                    <button className="btn-ghost-sm" onClick={() => startConfigure(node)}>
                      Configure
                    </button>
                  ) : (
                    <>
                      <button className="btn-ghost-sm" onClick={() => startEdit(node)}>
                        Edit
                      </button>
                      <button className="infra-delete-btn" onClick={() => handleDelete(node.id)}>
                        Remove
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {filteredNodes.length === 0 && (
          <p className="muted" style={{ fontSize: "0.73rem", padding: "4px 0" }}>
            No nodes match the current search.
          </p>
        )}
      </div>

      {showForm && (
        <form className="infra-add-form" onSubmit={handleAdd}>
          <div className="infra-form-row">
            <input
              className="infra-input"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Node name *"
              required
            />
            <select
              className="infra-input"
              value={form.type}
              onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
            >
              {NODE_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="infra-form-row">
            <input
              className="infra-input"
              value={form.hostname}
              onChange={(e) => setForm((f) => ({ ...f, hostname: e.target.value }))}
              placeholder="Hostname / IP"
            />
            <input
              className="infra-input"
              value={form.tailscale_name}
              onChange={(e) => setForm((f) => ({ ...f, tailscale_name: e.target.value }))}
              placeholder="Tailscale name"
            />
          </div>
          <div className="infra-form-row">
            <input
              className="infra-input"
              value={form.agent_url}
              onChange={(e) => setForm((f) => ({ ...f, agent_url: e.target.value }))}
              placeholder="Agent URL (e.g. http://100.64.1.5:8765)"
              style={{ flex: 1 }}
            />
          </div>
          <div className="infra-form-row">
            <input
              className="infra-input"
              value={form.tags}
              onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))}
              placeholder="Tags (comma-separated)"
              style={{ flex: 1 }}
            />
            <button
              type="submit"
              className="panel-button"
              disabled={submitting || !form.name.trim()}
              style={{ flexShrink: 0 }}
            >
              {submitting ? "Adding..." : "Add"}
            </button>
          </div>
          <div className="infra-form-row">
            <input
              className="infra-input"
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Notes"
              style={{ flex: 1 }}
            />
          </div>
        </form>
      )}
    </section>
  );
}
