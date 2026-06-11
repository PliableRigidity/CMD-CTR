import { useMemo, useState } from "react";

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

export default function InfrastructurePanel({ nodes = [], onAddNode, onSaveNode, onProbeNode, onDeleteNode }) {
  const [expanded, setExpanded] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [probingId, setProbingId] = useState(null);

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
                {node.services && node.services.length > 0 && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Services</span>
                    <span>
                      {node.services.map((s) => (
                        <span key={s} className="infra-tag">{s}</span>
                      ))}
                    </span>
                  </div>
                )}
                {node.capabilities && node.capabilities.length > 0 && (
                  <div className="infra-detail-row">
                    <span className="infra-detail-label">Capabilities</span>
                    <span className="muted" style={{ fontSize: "0.7rem" }}>
                      {node.capabilities.join(", ")}
                    </span>
                  </div>
                )}
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
                <div className="button-row">
                  <button className="btn-ghost-sm" onClick={() => handleProbe(node.id)} disabled={probingId === node.id}>
                    {probingId === node.id ? "Probing..." : "Probe"}
                  </button>
                  {node.id !== "workstation" && (
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
