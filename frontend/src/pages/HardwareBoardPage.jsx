import { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import {
  fetchHardwareSummary,
  fetchHardwareInventory,
  fetchHardwareProjects,
  fetchHardwareProject,
  fetchHardwareOrders,
  createHardwarePart,
  updateHardwarePart,
  deleteHardwarePart,
  createHardwareProject,
  updateHardwareProject,
  deleteHardwareProject,
  assignPartToProject,
  unassignPartFromProject,
  createHardwareOrder,
  updateHardwareOrderStatus,
  deleteHardwareOrder,
  fetchHardwareReadiness,
  fetchHardwareMissingParts,
  fetchHardwareRecommendations,
  fetchHardwarePriority,
  fetchHardwareImports,
  importHardwareFile,
  sendHardwareAssistantMessage,
  fetchHardwareLowStock,
  fetchHardwareAfterDelivery,
  receiveHardwareOrder,
} from "../lib/api";

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
  green:     "#4ade80",
  orange:    "#fb923c",
  red:       "#f87171",
  blue:      "#60a5fa",
  purple:    "#a78bfa",
};

const STATUS_COLOR = {
  // Inventory
  "in-stock":         T.green,
  "low-stock":        T.orange,
  "out-of-stock":     T.red,
  "on-order":         T.blue,
  // Project — 10-state model
  "planned":          T.textMuted,
  "researching":      T.blue,
  "designing":        T.purple,
  "ordering":         T.orange,
  "waiting_for_parts": "#f59e0b",
  "building":         "#22c55e",
  "testing":          "#38bdf8",
  "blocked":          T.red,
  "completed":        T.green,
  "archived":         "#374151",
  // Legacy project statuses
  "active":           T.green,
  "paused":           T.textMuted,
  "complete":         T.blue,
  "abandoned":        T.red,
  // Orders
  "ordered":          T.orange,
  "manufacturing":    T.purple,
  "shipped":          T.blue,
  "in_transit":       "#38bdf8",
  "delivered":        T.green,
  "cancelled":        T.red,
};

const PRIORITY_COLOR = {
  critical: T.red,
  high:     T.orange,
  normal:   T.gold,
  low:      T.textMuted,
};

const CATEGORY_ICONS = {
  microcontroller:  "⚡",
  mcu:              "⚡",
  sbc:              "🖥",
  sensor:           "📡",
  gps_gnss:         "📍",
  gps:              "📍",
  gnss:             "📍",
  display:          "🖥",
  motor:            "⚙️",
  battery:          "🔋",
  power:            "🔌",
  radio:            "📶",
  audio:            "🔊",
  storage:          "💾",
  pcb:              "🔲",
  module:           "🧩",
  passive_component:"🔩",
  misc:             "📦",
};

function catIcon(cat) {
  return CATEGORY_ICONS[(cat || "misc").toLowerCase()] || "📦";
}

// ── Shared UI atoms ───────────────────────────────────────────────────────────

function parseCsvPreview(text, maxRows = 8) {
  const rows = [];
  let cell = "";
  let row = [];
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const next = text[i + 1];
    if (ch === '"' && quoted && next === '"') {
      cell += '"';
      i++;
    } else if (ch === '"') {
      quoted = !quoted;
    } else if (ch === "," && !quoted) {
      row.push(cell.trim());
      cell = "";
    } else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && next === "\n") i++;
      row.push(cell.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      cell = "";
      if (rows.length > maxRows) break;
    } else {
      cell += ch;
    }
  }
  if (cell || row.length) {
    row.push(cell.trim());
    if (row.some(Boolean)) rows.push(row);
  }
  return { headers: rows[0] || [], rows: rows.slice(1, maxRows + 1) };
}

async function createImportPreview(file, sourceType) {
  const ext = file.name.split(".").pop()?.toLowerCase() || "";
  const base = {
    file,
    fileName: file.name,
    sourceType,
    project: "",
    size: file.size,
    headers: [],
    rows: [],
    warning: "Backend commit resolves this file by filename in indexed trusted locations.",
    error: "",
  };
  if (ext === "csv") {
    const preview = parseCsvPreview(await file.text());
    return { ...base, ...preview };
  }
  if (ext === "xlsx" || ext === "xlsm") {
    return {
      ...base,
      warning: "XLSX selected. Preview is metadata-only in the browser; backend parses rows if openpyxl is installed and the file is indexed.",
    };
  }
  return { ...base, error: "Unsupported file type. Choose CSV or XLSX." };
}

function Badge({ status, small }) {
  const color = STATUS_COLOR[status] || T.textMuted;
  return (
    <span style={{
      fontSize: small ? "9px" : "10px",
      fontFamily: "JetBrains Mono, monospace",
      color,
      border: `1px solid ${color}33`,
      borderRadius: 3,
      padding: "1px 5px",
      textTransform: "uppercase",
      letterSpacing: "0.05em",
      whiteSpace: "nowrap",
    }}>
      {status}
    </span>
  );
}

function PriorityDot({ priority }) {
  return (
    <span style={{
      width: 6, height: 6, borderRadius: "50%",
      background: PRIORITY_COLOR[priority] || T.textMuted,
      display: "inline-block", flexShrink: 0,
    }} />
  );
}

function SectionHeader({ title, count, action, actionLabel }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <h2 style={{ margin: 0, fontSize: 11, fontFamily: "JetBrains Mono, monospace",
          color: T.gold, letterSpacing: "0.12em", textTransform: "uppercase" }}>
          {title}
        </h2>
        {count != null && (
          <span style={{ fontSize: 10, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
            {count}
          </span>
        )}
      </div>
      {action && (
        <button onClick={action} style={{
          background: "none", border: `1px solid ${T.borderHi}`, color: T.gold,
          fontSize: 10, padding: "2px 8px", borderRadius: 3, cursor: "pointer",
          fontFamily: "JetBrains Mono, monospace",
        }}>
          {actionLabel || "＋"}
        </button>
      )}
    </div>
  );
}

function Panel({ children, style }) {
  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      borderRadius: 6,
      padding: 16,
      ...style,
    }}>
      {children}
    </div>
  );
}

function EmptyState({ msg }) {
  return (
    <p style={{ fontSize: 11, color: T.textMuted, fontFamily: "JetBrains Mono, monospace",
      textAlign: "center", padding: "24px 0" }}>
      {msg}
    </p>
  );
}

function IconBtn({ onClick, title, children, danger }) {
  return (
    <button onClick={onClick} title={title} style={{
      background: "none", border: "none", cursor: "pointer",
      color: danger ? T.red : T.textMuted, fontSize: 12, padding: "1px 4px",
      opacity: 0.6, lineHeight: 1,
    }}
      onMouseEnter={e => e.currentTarget.style.opacity = "1"}
      onMouseLeave={e => e.currentTarget.style.opacity = "0.6"}
    >
      {children}
    </button>
  );
}

// ── Add-Part Modal ────────────────────────────────────────────────────────────

function AddPartModal({ onClose, onSave, prefill }) {
  const [form, setForm] = useState({
    name: prefill?.name || "",
    category: prefill?.category || "misc",
    quantity: prefill?.quantity ?? 1,
    subcategory: prefill?.subcategory || "",
    manufacturer: prefill?.manufacturer || "",
    part_number: prefill?.part_number || "",
    location: prefill?.location || "",
    notes: prefill?.notes || "",
    datasheet_url: prefill?.datasheet_url || "",
    status: prefill?.status || "in-stock",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const field = (key) => ({
    value: form[key],
    onChange: e => setForm(f => ({ ...f, [key]: e.target.value })),
    style: inputStyle,
  });

  async function handleSave() {
    if (!form.name.trim()) { setError("Name is required."); return; }
    setSaving(true);
    try {
      await onSave({ ...form, quantity: parseInt(form.quantity) || 0 });
      onClose();
    } catch (e) {
      setError(e.message || "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalWrapper onClose={onClose} title={prefill?.id ? "Edit Component" : "Add Component"}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <label style={labelStyle}>
          Name *
          <input {...field("name")} placeholder="ESP32-S3" />
        </label>
        <label style={labelStyle}>
          Category
          <input {...field("category")} placeholder="microcontroller" />
        </label>
        <label style={labelStyle}>
          Quantity
          <input {...field("quantity")} type="number" min={0} />
        </label>
        <label style={labelStyle}>
          Status
          <select {...field("status")} style={inputStyle}>
            {["in-stock","low-stock","out-of-stock","on-order"].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label style={labelStyle}>
          Manufacturer
          <input {...field("manufacturer")} placeholder="Espressif" />
        </label>
        <label style={labelStyle}>
          Part Number
          <input {...field("part_number")} placeholder="ESP32-S3-WROOM-1" />
        </label>
        <label style={labelStyle}>
          Location
          <input {...field("location")} placeholder="Drawer A3" />
        </label>
        <label style={labelStyle}>
          Subcategory
          <input {...field("subcategory")} placeholder="WiFi+BLE" />
        </label>
        <label style={{ ...labelStyle, gridColumn: "1/-1" }}>
          Notes
          <input {...field("notes")} placeholder="Main MCU for DroneHive" />
        </label>
        <label style={{ ...labelStyle, gridColumn: "1/-1" }}>
          Datasheet URL
          <input {...field("datasheet_url")} placeholder="https://..." />
        </label>
      </div>
      {error && <p style={{ color: T.red, fontSize: 11, marginTop: 8 }}>{error}</p>}
      <ModalButtons onClose={onClose} onSave={handleSave} saving={saving} />
    </ModalWrapper>
  );
}

// ── Add-Project Modal ─────────────────────────────────────────────────────────

function AddProjectModal({ onClose, onSave, prefill }) {
  const [form, setForm] = useState({
    name: prefill?.name || "",
    status: prefill?.status || "active",
    priority: prefill?.priority || "normal",
    description: prefill?.description || "",
    notes: prefill?.notes || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const field = (key) => ({
    value: form[key],
    onChange: e => setForm(f => ({ ...f, [key]: e.target.value })),
    style: inputStyle,
  });

  async function handleSave() {
    if (!form.name.trim()) { setError("Name is required."); return; }
    setSaving(true);
    try {
      await onSave(form);
      onClose();
    } catch (e) {
      setError(e.message || "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalWrapper onClose={onClose} title={prefill?.id ? "Edit Project" : "New Hardware Project"}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <label style={{ ...labelStyle, gridColumn: "1/-1" }}>
          Project Name *
          <input {...field("name")} placeholder="DroneHive" />
        </label>
        <label style={labelStyle}>
          Status
          <select {...field("status")} style={inputStyle}>
            {["planned","researching","designing","ordering","waiting_for_parts",
              "building","testing","blocked","completed","archived",
              "active","paused"].map(s => (
              <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
            ))}
          </select>
        </label>
        <label style={labelStyle}>
          Priority
          <select {...field("priority")} style={inputStyle}>
            {["low","normal","high","critical"].map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, gridColumn: "1/-1" }}>
          Description
          <input {...field("description")} placeholder="Autonomous drone swarm controller" />
        </label>
        <label style={{ ...labelStyle, gridColumn: "1/-1" }}>
          Notes
          <input {...field("notes")} />
        </label>
      </div>
      {error && <p style={{ color: T.red, fontSize: 11, marginTop: 8 }}>{error}</p>}
      <ModalButtons onClose={onClose} onSave={handleSave} saving={saving} />
    </ModalWrapper>
  );
}

// ── Add-Order Modal ───────────────────────────────────────────────────────────

function AddOrderModal({ onClose, onSave }) {
  const [form, setForm] = useState({ part_name: "", vendor: "", quantity: 1, notes: "", status: "ordered" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const field = (key) => ({
    value: form[key],
    onChange: e => setForm(f => ({ ...f, [key]: e.target.value })),
    style: inputStyle,
  });

  async function handleSave() {
    if (!form.part_name.trim()) { setError("Part name is required."); return; }
    setSaving(true);
    try {
      await onSave({ ...form, quantity: parseInt(form.quantity) || 1 });
      onClose();
    } catch (e) {
      setError(e.message || "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ModalWrapper onClose={onClose} title="Log Order">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <label style={{ ...labelStyle, gridColumn: "1/-1" }}>
          Part Name *
          <input {...field("part_name")} placeholder="ESP32-S3" />
        </label>
        <label style={labelStyle}>
          Vendor
          <input {...field("vendor")} placeholder="AliExpress" />
        </label>
        <label style={labelStyle}>
          Quantity
          <input {...field("quantity")} type="number" min={1} />
        </label>
        <label style={labelStyle}>
          Status
          <select {...field("status")} style={inputStyle}>
            {["ordered","manufacturing","in_transit","shipped","delivered","cancelled"].map(s => (
              <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
            ))}
          </select>
        </label>
        <label style={labelStyle}>
          Notes
          <input {...field("notes")} />
        </label>
      </div>
      {error && <p style={{ color: T.red, fontSize: 11, marginTop: 8 }}>{error}</p>}
      <ModalButtons onClose={onClose} onSave={handleSave} saving={saving} />
    </ModalWrapper>
  );
}

// ── Project Detail Modal ──────────────────────────────────────────────────────

function ProjectDetailModal({ projectId, allParts, onClose, onRefresh }) {
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [assignPart, setAssignPart] = useState("");
  const [assignQty, setAssignQty] = useState(1);
  const [assigning, setAssigning] = useState(false);

  useEffect(() => {
    fetchHardwareProject(projectId).then(setProject).catch(() => {}).finally(() => setLoading(false));
  }, [projectId]);

  async function doAssign() {
    const part = allParts.find(p => p.name.toLowerCase() === assignPart.trim().toLowerCase());
    if (!part) { alert(`Part not found: ${assignPart}`); return; }
    setAssigning(true);
    try {
      await assignPartToProject(projectId, part.id, assignQty);
      const updated = await fetchHardwareProject(projectId);
      setProject(updated);
      setAssignPart("");
      setAssignQty(1);
      onRefresh();
    } catch (e) {
      alert(e.message);
    } finally {
      setAssigning(false);
    }
  }

  async function doUnassign(partId) {
    await unassignPartFromProject(projectId, partId);
    const updated = await fetchHardwareProject(projectId);
    setProject(updated);
    onRefresh();
  }

  const STAT_ORDER = [
    "planned","researching","designing","ordering","waiting_for_parts",
    "building","testing","blocked","completed","archived",
    "active","paused","complete","abandoned",
  ];

  return (
    <ModalWrapper onClose={onClose} title={project ? project.name : "Loading…"} wide>
      {loading && <p style={{ color: T.textMuted, fontSize: 11 }}>Loading…</p>}
      {project && (
        <>
          <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <Badge status={project.status} />
            <Badge status={project.priority} />
            {project.description && (
              <span style={{ fontSize: 11, color: T.textMuted }}>{project.description}</span>
            )}
          </div>

          {/* Status selector */}
          <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
            {STAT_ORDER.map(s => (
              <button key={s} onClick={async () => {
                await updateHardwareProject(projectId, { status: s });
                const updated = await fetchHardwareProject(projectId);
                setProject(updated);
                onRefresh();
              }} style={{
                fontSize: 9, padding: "2px 8px", borderRadius: 3, cursor: "pointer",
                fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase",
                border: `1px solid ${project.status === s ? (STATUS_COLOR[s] || T.gold) : T.border}`,
                background: project.status === s ? `${STATUS_COLOR[s]}18` : "none",
                color: project.status === s ? (STATUS_COLOR[s] || T.gold) : T.textMuted,
              }}>
                {s}
              </button>
            ))}
          </div>

          {/* Parts table */}
          <p style={{ fontSize: 10, color: T.gold, letterSpacing: "0.1em",
            textTransform: "uppercase", marginBottom: 8 }}>
            Required Parts ({project.parts?.length || 0})
            {project.missing?.length > 0 && (
              <span style={{ color: T.orange, marginLeft: 8 }}>
                — {project.missing.length} missing / low stock
              </span>
            )}
          </p>
          <div style={{ marginBottom: 14 }}>
            {(project.parts || []).length === 0 && (
              <EmptyState msg="No parts assigned yet." />
            )}
            {(project.parts || []).map(p => {
              const available = p.available_qty ?? p.stock_qty ?? 0;
              const ok = available >= (p.quantity_required || 1);
              return (
                <div key={p.part_id} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "5px 0", borderBottom: `1px solid ${T.border}`,
                  fontSize: 11, fontFamily: "JetBrains Mono, monospace",
                }}>
                  <span style={{ color: ok ? T.green : T.orange, width: 12 }}>
                    {ok ? "✓" : "✗"}
                  </span>
                  <span style={{ flex: 1, color: T.text }}>
                    {p.name}
                    {p.source && (
                      <span style={{ color: T.textMuted, marginLeft: 6 }}>({p.source})</span>
                    )}
                    {(p.acceptable_substitutes || []).length > 0 && (
                      <span style={{ display: "block", color: T.cyan, fontSize: 9 }}>
                        substitutes: {p.acceptable_substitutes.join(", ")}
                      </span>
                    )}
                  </span>
                  <span style={{ color: T.textMuted }}>
                    need: {p.quantity_required}  available: {available}
                  </span>
                  <Badge status={p.stock_status || "in-stock"} small />
                  <IconBtn onClick={() => doUnassign(p.part_id)} title="Unassign" danger>×</IconBtn>
                </div>
              );
            })}
          </div>

          {/* Assign a part */}
          <p style={{ fontSize: 10, color: T.gold, letterSpacing: "0.1em",
            textTransform: "uppercase", marginBottom: 6 }}>
            Assign Part
          </p>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              value={assignPart}
              onChange={e => setAssignPart(e.target.value)}
              placeholder="Part name…"
              list="hw-part-list"
              style={{ ...inputStyle, flex: 1 }}
            />
            <datalist id="hw-part-list">
              {allParts.map(p => <option key={p.id} value={p.name} />)}
            </datalist>
            <input
              type="number" min={1}
              value={assignQty}
              onChange={e => setAssignQty(parseInt(e.target.value) || 1)}
              style={{ ...inputStyle, width: 60 }}
            />
            <button onClick={doAssign} disabled={assigning || !assignPart.trim()} style={{
              background: `${T.gold}22`, border: `1px solid ${T.gold}66`,
              color: T.gold, fontSize: 11, padding: "4px 12px", borderRadius: 3, cursor: "pointer",
              fontFamily: "JetBrains Mono, monospace",
            }}>
              {assigning ? "…" : "Assign"}
            </button>
          </div>
        </>
      )}
    </ModalWrapper>
  );
}

// ── Shared modal chrome ───────────────────────────────────────────────────────

function ModalWrapper({ children, onClose, title, wide }) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 100,
      background: "rgba(6,11,20,0.88)", display: "flex",
      alignItems: "center", justifyContent: "center",
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: T.surface, border: `1px solid ${T.borderHi}`,
        borderRadius: 8, padding: 24,
        width: wide ? 640 : 480, maxWidth: "95vw",
        maxHeight: "90vh", overflowY: "auto",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 13, color: T.gold,
            fontFamily: "JetBrains Mono, monospace", letterSpacing: "0.05em" }}>
            {title}
          </h3>
          <button onClick={onClose} style={{
            background: "none", border: "none", color: T.textMuted,
            fontSize: 18, cursor: "pointer", lineHeight: 1,
          }}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ModalButtons({ onClose, onSave, saving }) {
  return (
    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
      <button onClick={onClose} style={{
        background: "none", border: `1px solid ${T.border}`,
        color: T.textMuted, fontSize: 11, padding: "5px 14px", borderRadius: 3, cursor: "pointer",
        fontFamily: "JetBrains Mono, monospace",
      }}>
        Cancel
      </button>
      <button onClick={onSave} disabled={saving} style={{
        background: `${T.gold}22`, border: `1px solid ${T.gold}66`,
        color: T.gold, fontSize: 11, padding: "5px 14px", borderRadius: 3, cursor: "pointer",
        fontFamily: "JetBrains Mono, monospace",
      }}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}

const inputStyle = {
  display: "block", width: "100%", boxSizing: "border-box",
  background: "#080f1c", border: `1px solid ${T.border}`,
  borderRadius: 3, padding: "5px 8px", color: T.text,
  fontSize: 11, fontFamily: "JetBrains Mono, monospace",
  outline: "none", marginTop: 3,
};

const labelStyle = {
  display: "block", fontSize: 10, color: T.textMuted,
  fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase",
  letterSpacing: "0.05em",
};

// ── Inventory Panel ───────────────────────────────────────────────────────────

function InventoryPanel({ parts, cats, onAdd, onEdit, onDelete, search, onSearch }) {
  const [expandedCat, setExpandedCat] = useState(null);
  const [filter, setFilter] = useState("all");

  const filtered = search
    ? parts.filter(p =>
        p.name.toLowerCase().includes(search.toLowerCase()) ||
        p.category.toLowerCase().includes(search.toLowerCase()) ||
        (p.manufacturer || "").toLowerCase().includes(search.toLowerCase())
      )
    : filter === "all" ? parts : parts.filter(p => p.category === filter);

  const grouped = {};
  for (const p of filtered) {
    const c = p.category || "misc";
    (grouped[c] = grouped[c] || []).push(p);
  }

  return (
    <Panel style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <SectionHeader title="Inventory" count={`${parts.length} types`} action={onAdd} actionLabel="＋ Add" />

      {/* Search */}
      <div style={{ marginBottom: 10 }}>
        <input
          value={search}
          onChange={e => onSearch(e.target.value)}
          placeholder="Search parts…"
          style={{ ...inputStyle, marginTop: 0 }}
        />
      </div>

      {/* Category filter chips */}
      {!search && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
          <button onClick={() => setFilter("all")} style={chipStyle(filter === "all")}>
            All ({parts.length})
          </button>
          {cats.map(c => (
            <button key={c.category} onClick={() => setFilter(c.category === filter ? "all" : c.category)}
              style={chipStyle(filter === c.category)}>
              {catIcon(c.category)} {c.category} ({c.count})
            </button>
          ))}
        </div>
      )}

      {/* Part list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.length === 0 && <EmptyState msg="No components found." />}
        {Object.entries(grouped).sort().map(([cat, items]) => (
          <div key={cat} style={{ marginBottom: 4 }}>
            <button onClick={() => setExpandedCat(expandedCat === cat ? null : cat)} style={{
              background: "none", border: "none", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 6, width: "100%",
              padding: "5px 0", color: T.goldDim,
              fontSize: 10, fontFamily: "JetBrains Mono, monospace",
              textTransform: "uppercase", letterSpacing: "0.08em",
            }}>
              <span>{expandedCat === cat ? "▾" : "▸"}</span>
              <span>{catIcon(cat)} {cat}</span>
              <span style={{ marginLeft: "auto", color: T.textMuted }}>
                {items.length} types · {items.reduce((s, p) => s + (p.quantity || 0), 0)} units
              </span>
            </button>

            {(expandedCat === cat || search || filter !== "all") && items.map(p => (
              <div key={p.id} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "4px 0 4px 16px",
                borderBottom: `1px solid ${T.border}22`,
                fontSize: 11, fontFamily: "JetBrains Mono, monospace",
              }}>
                <span style={{ flex: 1, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {p.name}
                </span>
                <span style={{ color: T.textMuted, minWidth: 40, textAlign: "right" }}>
                  ×{p.quantity}
                </span>
                <Badge status={p.status || "in-stock"} small />
                <IconBtn onClick={() => onEdit(p)} title="Edit">✎</IconBtn>
                <IconBtn onClick={() => onDelete(p)} title="Delete" danger>×</IconBtn>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function chipStyle(active) {
  return {
    background: active ? `${T.gold}22` : "none",
    border: `1px solid ${active ? T.gold + "88" : T.border}`,
    color: active ? T.gold : T.textMuted,
    fontSize: 9, padding: "2px 7px", borderRadius: 12,
    cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
    textTransform: "uppercase", letterSpacing: "0.05em",
  };
}

// ── Projects Panel ────────────────────────────────────────────────────────────

function ProjectsPanel({ projects, allParts, onAdd, onEdit, onDelete, onRefresh }) {
  const [detailId, setDetailId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = statusFilter === "all" ? projects
    : projects.filter(p => p.status === statusFilter);

  const statusCounts = {};
  for (const p of projects) statusCounts[p.status] = (statusCounts[p.status] || 0) + 1;

  return (
    <Panel style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <SectionHeader title="Projects" count={`${projects.length} total`} action={onAdd} actionLabel="＋ New" />

      {/* Status filter — dynamic based on what exists */}
      <div style={{ display: "flex", gap: 4, marginBottom: 10, flexWrap: "wrap" }}>
        <button onClick={() => setStatusFilter("all")} style={chipStyle(statusFilter === "all")}>
          All ({projects.length})
        </button>
        {Object.keys(statusCounts).sort().map(s => (
          <button key={s} onClick={() => setStatusFilter(s === statusFilter ? "all" : s)}
            style={chipStyle(statusFilter === s)}>
            {s.replace(/_/g, " ")} ({statusCounts[s]})
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.length === 0 && <EmptyState msg="No projects found." />}
        {filtered.map(p => (
          <div key={p.id} style={{
            padding: "9px 0", borderBottom: `1px solid ${T.border}`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <PriorityDot priority={p.priority} />
              <button onClick={() => setDetailId(p.id)} style={{
                background: "none", border: "none", cursor: "pointer",
                color: T.text, fontSize: 12, fontFamily: "JetBrains Mono, monospace",
                textAlign: "left", flex: 1, padding: 0,
              }}>
                {p.name}
              </button>
              <Badge status={p.status} small />
              <IconBtn onClick={() => onEdit(p)} title="Edit">✎</IconBtn>
              <IconBtn onClick={() => onDelete(p)} title="Delete" danger>×</IconBtn>
            </div>
            {p.description && (
              <p style={{ margin: "3px 0 0 14px", fontSize: 10, color: T.textMuted,
                fontFamily: "JetBrains Mono, monospace", overflow: "hidden",
                textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {p.description}
              </p>
            )}
          </div>
        ))}
      </div>

      {detailId && (
        <ProjectDetailModal
          projectId={detailId}
          allParts={allParts}
          onClose={() => setDetailId(null)}
          onRefresh={onRefresh}
        />
      )}
    </Panel>
  );
}

// ── Orders Panel ──────────────────────────────────────────────────────────────

const ORDER_STATUS_FLOW = ["ordered", "manufacturing", "shipped", "delivered", "cancelled"];

function OrdersPanel({ orders, onAdd, onDelete, onRefresh }) {
  const [tab, setTab] = useState("active");

  const active = orders.filter(o => ["ordered","manufacturing","shipped"].includes(o.status));
  const done   = orders.filter(o => ["delivered","cancelled"].includes(o.status));
  const shown  = tab === "active" ? active : done;

  async function advance(order) {
    const idx = ORDER_STATUS_FLOW.indexOf(order.status);
    if (idx < 0 || idx >= ORDER_STATUS_FLOW.length - 2) return;
    const next = ORDER_STATUS_FLOW[idx + 1];
    await updateHardwareOrderStatus(order.id, next);
    onRefresh();
  }

  return (
    <Panel style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <SectionHeader title="Orders" count={`${active.length} active`} action={onAdd} actionLabel="＋ Log" />

      {/* Tab */}
      <div style={{ display: "flex", gap: 4, marginBottom: 10 }}>
        <button onClick={() => setTab("active")} style={chipStyle(tab === "active")}>
          Active ({active.length})
        </button>
        <button onClick={() => setTab("done")} style={chipStyle(tab === "done")}>
          Completed ({done.length})
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {shown.length === 0 && <EmptyState msg={tab === "active" ? "No active orders." : "No completed orders."} />}
        {shown.map(o => (
          <div key={o.id} style={{
            padding: "8px 0", borderBottom: `1px solid ${T.border}`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Badge status={o.status} small />
              <span style={{
                flex: 1, fontSize: 11, color: T.text,
                fontFamily: "JetBrains Mono, monospace",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {o.part_name}
              </span>
              <span style={{ fontSize: 10, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
                ×{o.quantity}
              </span>
              {tab === "active" && o.status !== "shipped" && (
                <button onClick={() => advance(o)} title="Advance status" style={{
                  background: "none", border: `1px solid ${T.border}`,
                  color: T.gold, fontSize: 9, padding: "1px 6px",
                  borderRadius: 3, cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
                }}>
                  →
                </button>
              )}
              {tab === "active" && o.status === "shipped" && (
                <button onClick={() => { updateHardwareOrderStatus(o.id, "delivered").then(onRefresh); }}
                  style={{
                    background: `${T.green}15`, border: `1px solid ${T.green}44`,
                    color: T.green, fontSize: 9, padding: "1px 6px",
                    borderRadius: 3, cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
                  }}>
                  Delivered
                </button>
              )}
              <IconBtn onClick={() => onDelete(o)} title="Delete" danger>×</IconBtn>
            </div>
            {o.vendor && (
              <p style={{ margin: "2px 0 0 0", fontSize: 10, color: T.textMuted,
                fontFamily: "JetBrains Mono, monospace" }}>
                {o.vendor} · {o.id}
              </p>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ── Project Intelligence Components ──────────────────────────────────────────

function ImportsPanel({ imports, onFileSelected }) {
  const bomInputRef = useRef(null);
  const inventoryInputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  function handleInput(type, event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onFileSelected(file, type);
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    const type = /inventory|stock/i.test(file.name) ? "inventory" : "bom";
    onFileSelected(file, type);
  }

  return (
    <Panel style={{ marginBottom: 16, flexShrink: 0 }}>
      <SectionHeader title="Imports" count={`${imports.length} recent`} />
      <input
        ref={bomInputRef}
        type="file"
        accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        style={{ display: "none" }}
        onChange={(event) => handleInput("bom", event)}
      />
      <input
        ref={inventoryInputRef}
        type="file"
        accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        style={{ display: "none" }}
        onChange={(event) => handleInput("inventory", event)}
      />
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button onClick={() => bomInputRef.current?.click()} style={{
          flex: 1, background: "none", border: `1px solid ${T.borderHi}`,
          color: T.gold, fontSize: 10, padding: "5px 8px", borderRadius: 3,
          cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
        }}>
          Import BOM
        </button>
        <button onClick={() => inventoryInputRef.current?.click()} style={{
          flex: 1, background: "none", border: `1px solid ${T.border}`,
          color: T.text, fontSize: 10, padding: "5px 8px", borderRadius: 3,
          cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
        }}>
          Import Inventory
        </button>
      </div>
      <div
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        style={{
          border: `1px dashed ${dragging ? T.gold : T.border}`,
          background: dragging ? "rgba(201,148,58,0.08)" : "rgba(0,0,0,0.12)",
          borderRadius: 5,
          padding: 12,
          marginBottom: 12,
          textAlign: "center",
          color: dragging ? T.gold : T.textMuted,
          fontSize: 10,
          fontFamily: "JetBrains Mono, monospace",
        }}
      >
        Drop CSV/XLSX BOM or inventory files here
      </div>
      {!imports.length && <EmptyState msg="No BOM or inventory imports yet." />}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {imports.slice(0, 5).map(item => (
          <div key={item.id} style={{
            border: `1px solid ${T.border}`, borderRadius: 4, padding: 8,
            background: "rgba(0,0,0,0.16)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ fontSize: 10, color: T.gold, fontFamily: "JetBrains Mono, monospace",
                textTransform: "uppercase" }}>
                {item.source_type}
              </span>
              <span style={{ fontSize: 10, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>
                {item.imported_count} parts
              </span>
            </div>
            <p style={{ margin: "4px 0 0", fontSize: 11, color: T.text }}>
              {item.project_name || "Inventory import"}
            </p>
            <p style={{ margin: "2px 0 0", fontSize: 9, color: T.textMuted,
              fontFamily: "JetBrains Mono, monospace", overflow: "hidden",
              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {item.source_path}
            </p>
            {!!item.errors?.length && (
              <p style={{ margin: "4px 0 0", fontSize: 10, color: T.orange }}>
                {item.errors.length} validation warning(s)
              </p>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function HardwareAssistantPanel({ onCommitted }) {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hardware Assistant ready. I can manage inventory, projects, orders, and BOMs only." },
  ]);
  const [input, setInput] = useState("");
  const [pendingAction, setPendingAction] = useState(null);
  const [busy, setBusy] = useState(false);

  async function send(textOverride = "") {
    const text = (textOverride || input).trim();
    if (!text || busy) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", text }]);
    setBusy(true);
    try {
      const result = await sendHardwareAssistantMessage(text, pendingAction);
      setMessages(prev => [...prev, { role: "assistant", text: result.reply || "Done." }]);
      setPendingAction(result.pending_action || null);
      if (result.committed) onCommitted?.();
    } catch (error) {
      setMessages(prev => [...prev, {
        role: "assistant",
        text: error?.message || "Hardware Assistant request failed.",
      }]);
    } finally {
      setBusy(false);
    }
  }

  function quick(text) {
    setInput(text);
  }

  return (
    <Panel style={{ marginBottom: 16, flexShrink: 0, display: "flex", flexDirection: "column", maxHeight: 360 }}>
      <SectionHeader title="Hardware Assistant" count={pendingAction ? "preview pending" : "restricted"} />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        {["show pending orders", "show imported BOMs", "show missing parts", "show project readiness"].map(text => (
          <button key={text} onClick={() => quick(text)} style={{
            background: "none", border: `1px solid ${T.border}`,
            color: T.textMuted, fontSize: 9, padding: "2px 6px",
            borderRadius: 999, cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
          }}>
            {text}
          </button>
        ))}
      </div>
      <div style={{
        flex: 1, minHeight: 120, maxHeight: 180, overflowY: "auto",
        border: `1px solid ${T.border}`, borderRadius: 5, padding: 8,
        background: "rgba(0,0,0,0.14)", marginBottom: 8,
      }}>
        {messages.map((msg, idx) => (
          <div key={idx} style={{
            marginBottom: 8, whiteSpace: "pre-wrap",
            color: msg.role === "assistant" ? T.text : T.gold,
            fontSize: 11, lineHeight: 1.35,
          }}>
            <span style={{ color: T.textMuted, fontFamily: "JetBrains Mono, monospace", fontSize: 9 }}>
              {msg.role === "assistant" ? "HW" : "YOU"}:
            </span>{" "}
            {msg.text}
          </div>
        ))}
      </div>
      <textarea
        value={input}
        onChange={event => setInput(event.target.value)}
        onKeyDown={event => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) send();
        }}
        placeholder={"I bought:\n5 ESP32-S3\n2 MPU6050"}
        rows={3}
        style={{
          width: "100%", resize: "vertical", background: "#08111d",
          color: T.text, border: `1px solid ${T.border}`, borderRadius: 4,
          padding: 8, fontSize: 11, fontFamily: "JetBrains Mono, monospace",
        }}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        {pendingAction && (
          <>
            <button onClick={() => send("confirm")} disabled={busy} style={{
              flex: 1, background: `${T.green}18`, border: `1px solid ${T.green}55`,
              color: T.green, fontSize: 10, padding: "5px 8px", borderRadius: 3,
              cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
            }}>
              Confirm
            </button>
            <button onClick={() => send("cancel")} disabled={busy} style={{
              flex: 1, background: "none", border: `1px solid ${T.border}`,
              color: T.textMuted, fontSize: 10, padding: "5px 8px", borderRadius: 3,
              cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
            }}>
              Cancel
            </button>
          </>
        )}
        <button onClick={() => send()} disabled={busy || !input.trim()} style={{
          flex: pendingAction ? 1 : "none", marginLeft: "auto",
          background: "none", border: `1px solid ${T.borderHi}`,
          color: input.trim() ? T.gold : T.textMuted,
          fontSize: 10, padding: "5px 10px", borderRadius: 3,
          cursor: input.trim() ? "pointer" : "not-allowed",
          fontFamily: "JetBrains Mono, monospace",
        }}>
          {busy ? "Working…" : "Send"}
        </button>
      </div>
    </Panel>
  );
}

function ImportPreviewModal({ draft, onChange, onCancel, onCommit, committing }) {
  if (!draft) return null;
  const canCommit = !draft.error && !committing;
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.68)", display: "flex",
      alignItems: "center", justifyContent: "center", padding: 24,
    }}>
      <div style={{
        width: "min(760px, 94vw)", maxHeight: "86vh", overflow: "auto",
        background: T.surface, border: `1px solid ${T.borderHi}`,
        borderRadius: 8, padding: 18, boxShadow: "0 20px 80px rgba(0,0,0,0.5)",
      }}>
        <SectionHeader title="Import Preview" count={draft.sourceType.toUpperCase()} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <div>
            <p style={{ margin: 0, fontSize: 10, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>File</p>
            <p style={{ margin: "2px 0 0", fontSize: 13, color: T.text }}>{draft.fileName}</p>
          </div>
          <div>
            <p style={{ margin: 0, fontSize: 10, color: T.textMuted, fontFamily: "JetBrains Mono, monospace" }}>Size</p>
            <p style={{ margin: "2px 0 0", fontSize: 13, color: T.text }}>{Math.round(draft.size / 1024)} KB</p>
          </div>
        </div>

        {draft.sourceType === "bom" && (
          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", fontSize: 10, color: T.textMuted,
              fontFamily: "JetBrains Mono, monospace", marginBottom: 4 }}>
              Project override (optional)
            </span>
            <input
              value={draft.project}
              onChange={(event) => onChange({ ...draft, project: event.target.value })}
              placeholder="Inferred from filename if blank"
              style={{
                width: "100%", background: "#08111d", color: T.text,
                border: `1px solid ${T.border}`, borderRadius: 4,
                padding: "7px 9px", fontSize: 12,
              }}
            />
          </label>
        )}

        {draft.warning && (
          <p style={{ margin: "0 0 12px", fontSize: 11, color: T.orange }}>
            {draft.warning}
          </p>
        )}
        {draft.error && (
          <p style={{ margin: "0 0 12px", fontSize: 11, color: T.red }}>
            {draft.error}
          </p>
        )}

        {draft.headers.length > 0 ? (
          <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 5 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr>
                  {draft.headers.slice(0, 8).map((header, idx) => (
                    <th key={idx} style={{ textAlign: "left", padding: 6, color: T.gold,
                      borderBottom: `1px solid ${T.border}`, fontFamily: "JetBrains Mono, monospace" }}>
                      {header || `Column ${idx + 1}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {draft.rows.map((row, rowIdx) => (
                  <tr key={rowIdx}>
                    {draft.headers.slice(0, 8).map((_, colIdx) => (
                      <td key={colIdx} style={{ padding: 6, color: T.textMuted,
                        borderBottom: `1px solid ${T.border}` }}>
                        {row[colIdx] || ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState msg="No row preview available for this file type." />
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
          <button onClick={onCancel} disabled={committing} style={{
            background: "none", border: `1px solid ${T.border}`, color: T.textMuted,
            padding: "6px 12px", borderRadius: 4, cursor: "pointer",
          }}>
            Cancel
          </button>
          <button onClick={onCommit} disabled={!canCommit} style={{
            background: canCommit ? `${T.gold}22` : "rgba(255,255,255,0.04)",
            border: `1px solid ${canCommit ? T.borderHi : T.border}`,
            color: canCommit ? T.gold : T.textMuted,
            padding: "6px 12px", borderRadius: 4,
            cursor: canCommit ? "pointer" : "not-allowed",
            fontFamily: "JetBrains Mono, monospace",
          }}>
            {committing ? "Importing…" : "Commit Import"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ReadinessBar({ pct, status }) {
  const color = pct === 100 ? T.green : pct >= 50 ? T.orange : T.red;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: "#1a2535", borderRadius: 2 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 2, transition: "width 0.3s" }} />
      </div>
      <span style={{ fontSize: 10, color, fontFamily: "JetBrains Mono, monospace", minWidth: 32, textAlign: "right" }}>
        {pct}%
      </span>
    </div>
  );
}

function IntelPanel({ title, children, badge, badgeColor }) {
  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 6, padding: 14, flex: 1, minWidth: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 10, color: T.gold, fontFamily: "JetBrains Mono, monospace",
          letterSpacing: "0.12em", textTransform: "uppercase" }}>
          {title}
        </h3>
        {badge != null && (
          <span style={{
            fontSize: 9, color: badgeColor || T.textMuted,
            border: `1px solid ${(badgeColor || T.textMuted) + "44"}`,
            borderRadius: 10, padding: "0 5px",
            fontFamily: "JetBrains Mono, monospace",
          }}>
            {badge}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

function BuildReadinessPanel({ readiness, loading }) {
  if (loading) return <IntelPanel title="Build Readiness"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!readiness.length) return <IntelPanel title="Build Readiness"><EmptyState msg="No active projects." /></IntelPanel>;

  const readyCount = readiness.filter(r => r.readiness_pct === 100).length;
  return (
    <IntelPanel title="Build Readiness" badge={`${readyCount} ready`} badgeColor={readyCount > 0 ? T.green : T.textMuted}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 200, overflowY: "auto" }}>
        {readiness.map(r => (
          <div key={r.project_id}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
              <span style={{ fontSize: 11, color: T.text, fontFamily: "JetBrains Mono, monospace",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "70%" }}>
                {r.project_name}
              </span>
              <span style={{ fontSize: 9, color: STATUS_COLOR[r.project_status] || T.textMuted,
                fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", flexShrink: 0 }}>
                {(r.project_status || "").replace(/_/g, " ")}
              </span>
            </div>
            <ReadinessBar pct={r.readiness_pct} status={r.status} />
          </div>
        ))}
      </div>
    </IntelPanel>
  );
}

function MissingPartsPanel({ missingParts, loading }) {
  const totalMissing = missingParts.reduce((s, p) => s + p.missing.length, 0);
  if (loading) return <IntelPanel title="Missing Parts"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!missingParts.length) return (
    <IntelPanel title="Missing Parts" badge="all clear" badgeColor={T.green}>
      <EmptyState msg="All required parts are in stock." />
    </IntelPanel>
  );
  return (
    <IntelPanel title="Missing Parts" badge={`${totalMissing} missing`} badgeColor={T.orange}>
      <div style={{ maxHeight: 200, overflowY: "auto" }}>
        {missingParts.map(entry => (
          <div key={entry.project_id} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 10, color: T.gold, fontFamily: "JetBrains Mono, monospace",
              letterSpacing: "0.05em", marginBottom: 4 }}>
              {entry.project_name}
              <span style={{ color: T.textMuted, marginLeft: 6 }}>
                [{(entry.project_status || "").replace(/_/g, " ")}]
              </span>
            </div>
            {entry.missing.map(m => (
              <div key={m.name} style={{
                display: "flex", gap: 6, padding: "2px 0",
                fontSize: 10, fontFamily: "JetBrains Mono, monospace",
              }}>
                <span style={{ color: T.red, width: 10, flexShrink: 0 }}>✗</span>
                <span style={{ flex: 1, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {m.name}
                </span>
                <span style={{ color: T.textMuted, flexShrink: 0 }}>
                  need:{m.quantity_required} have:{m.stock_qty}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </IntelPanel>
  );
}

function RecommendationsPanel({ recommendations, loading }) {
  const urgencyColor = { critical: T.red, high: T.orange, normal: T.gold };
  if (loading) return <IntelPanel title="Recommended Orders"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!recommendations.length) return (
    <IntelPanel title="Recommended Orders" badge="nothing needed" badgeColor={T.green}>
      <EmptyState msg="All required parts are sufficiently stocked." />
    </IntelPanel>
  );
  return (
    <IntelPanel title="Recommended Orders" badge={`${recommendations.length} items`} badgeColor={T.orange}>
      <div style={{ maxHeight: 200, overflowY: "auto" }}>
        {recommendations.map((r, i) => {
          const uc = urgencyColor[r.urgency] || T.gold;
          const projects = r.affected_projects.slice(0, 2).map(p => p.project_name).join(", ")
            + (r.affected_projects.length > 2 ? ` +${r.affected_projects.length - 2}` : "");
          return (
            <div key={i} style={{ padding: "5px 0", borderBottom: `1px solid ${T.border}22` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                  fontSize: 8, color: uc, border: `1px solid ${uc}44`,
                  borderRadius: 2, padding: "0 4px",
                  fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", flexShrink: 0,
                }}>
                  {r.urgency}
                </span>
                <span style={{ flex: 1, fontSize: 11, color: T.text,
                  fontFamily: "JetBrains Mono, monospace", overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.part_name}
                </span>
                <span style={{ fontSize: 10, color: T.gold, fontFamily: "JetBrains Mono, monospace", flexShrink: 0 }}>
                  ×{r.buy_quantity}
                </span>
              </div>
              <p style={{ margin: "2px 0 0 20px", fontSize: 9, color: T.textMuted,
                fontFamily: "JetBrains Mono, monospace" }}>
                have:{r.stock_qty} need:{r.total_needed} · {projects}
              </p>
            </div>
          );
        })}
      </div>
    </IntelPanel>
  );
}

function PriorityPanel({ priorities, loading }) {
  const recColor = {
    can_build: T.green, nearly_ready: "#4ade80", needs_parts: T.orange, many_missing: T.red,
  };
  if (loading) return <IntelPanel title="Project Priority"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!priorities.length) return <IntelPanel title="Project Priority"><EmptyState msg="No active projects." /></IntelPanel>;
  return (
    <IntelPanel title="Work On Next" badge={`${priorities.length} active`}>
      <div style={{ maxHeight: 200, overflowY: "auto" }}>
        {priorities.map((p, i) => {
          const rc = recColor[p.recommendation] || T.textMuted;
          const labels = { can_build: "BUILD", nearly_ready: "CLOSE", needs_parts: "PARTS", many_missing: "BLOCKED" };
          return (
            <div key={p.project_id} style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "5px 0", borderBottom: `1px solid ${T.border}22`,
              fontSize: 11, fontFamily: "JetBrains Mono, monospace",
            }}>
              <span style={{ color: T.textMuted, width: 16, flexShrink: 0 }}>{i + 1}.</span>
              <span style={{ flex: 1, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {p.project_name}
              </span>
              <span style={{ fontSize: 10, color: T.textMuted }}>{p.readiness_pct}%</span>
              <span style={{
                fontSize: 8, color: rc, border: `1px solid ${rc}44`,
                borderRadius: 2, padding: "0 4px", textTransform: "uppercase", flexShrink: 0,
              }}>
                {labels[p.recommendation] || p.recommendation}
              </span>
            </div>
          );
        })}
      </div>
    </IntelPanel>
  );
}

function IntelligenceSection({ readiness, missingParts, recommendations, priorities, loading }) {
  const [collapsed, setCollapsed] = useState(false);
  const blockedCount = missingParts.length;
  const criticalRecs = recommendations.filter(r => r.urgency === "critical").length;

  return (
    <div style={{ borderTop: `1px solid ${T.border}`, background: "#080f1c", flexShrink: 0 }}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          display: "flex", alignItems: "center", gap: 12, padding: "8px 20px",
          cursor: "pointer", userSelect: "none",
        }}
      >
        <span style={{ fontSize: 10, color: T.gold, fontFamily: "JetBrains Mono, monospace",
          letterSpacing: "0.15em", textTransform: "uppercase" }}>
          {collapsed ? "▸" : "▾"} Project Intelligence
        </span>
        {blockedCount > 0 && (
          <span style={{ fontSize: 9, color: T.orange, border: `1px solid ${T.orange}44`,
            borderRadius: 10, padding: "0 6px", fontFamily: "JetBrains Mono, monospace" }}>
            {blockedCount} projects w/ missing parts
          </span>
        )}
        {criticalRecs > 0 && (
          <span style={{ fontSize: 9, color: T.red, border: `1px solid ${T.red}44`,
            borderRadius: 10, padding: "0 6px", fontFamily: "JetBrains Mono, monospace" }}>
            {criticalRecs} critical shortages
          </span>
        )}
      </div>
      {!collapsed && (
        <div style={{ display: "flex", gap: 12, padding: "0 16px 16px" }}>
          <BuildReadinessPanel readiness={readiness} loading={loading} />
          <MissingPartsPanel missingParts={missingParts} loading={loading} />
          <RecommendationsPanel recommendations={recommendations} loading={loading} />
          <PriorityPanel priorities={priorities} loading={loading} />
        </div>
      )}
    </div>
  );
}

// ── Procurement Section (Phase 12E) ──────────────────────────────────────────

function ActiveOrdersPanel({ orders, onReceive, loading }) {
  const active = orders.filter(o => !["delivered", "cancelled"].includes(o.status));
  if (loading) return <IntelPanel title="Active Orders"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!active.length) return (
    <IntelPanel title="Active Orders" badge="none" badgeColor={T.textMuted}>
      <EmptyState msg="No active orders. Use 'order 5 Part-Name' in chat." />
    </IntelPanel>
  );
  return (
    <IntelPanel title="Active Orders" badge={`${active.length} pending`} badgeColor={T.orange}>
      <div style={{ maxHeight: 200, overflowY: "auto" }}>
        {active.slice(0, 20).map(o => (
          <div key={o.id} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "4px 0", borderBottom: `1px solid ${T.border}22`,
            fontSize: 10, fontFamily: "JetBrains Mono, monospace",
          }}>
            <span style={{ color: T.textMuted, flexShrink: 0, fontSize: 9 }}>[{o.id}]</span>
            <span style={{ flex: 1, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {o.part_name}
            </span>
            <span style={{ color: T.gold, flexShrink: 0 }}>×{o.quantity}</span>
            <Badge status={o.status} small />
            {onReceive && (
              <button onClick={() => onReceive(o)} title="Mark delivered + update inventory" style={{
                fontSize: 9, padding: "1px 5px", background: "none",
                border: `1px solid ${T.green}44`, color: T.green, borderRadius: 2,
                cursor: "pointer", fontFamily: "JetBrains Mono, monospace", flexShrink: 0,
              }}>
                ✓
              </button>
            )}
          </div>
        ))}
      </div>
    </IntelPanel>
  );
}

function LowStockPanel({ items, loading }) {
  if (loading) return <IntelPanel title="Low Stock"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!items.length) return (
    <IntelPanel title="Low Stock" badge="all clear" badgeColor={T.green}>
      <EmptyState msg="No items below reorder threshold." />
    </IntelPanel>
  );
  return (
    <IntelPanel title="Low Stock" badge={`${items.length} alerts`} badgeColor={T.red}>
      <div style={{ maxHeight: 200, overflowY: "auto" }}>
        {items.slice(0, 20).map(item => (
          <div key={item.id} style={{
            padding: "4px 0", borderBottom: `1px solid ${T.border}22`,
            fontSize: 10, fontFamily: "JetBrains Mono, monospace",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ color: T.text, overflow: "hidden", textOverflow: "ellipsis",
                whiteSpace: "nowrap", flex: 1 }}>
                {item.name}
              </span>
              <span style={{ color: T.red, flexShrink: 0 }}>{item.quantity} / {item.reorder_threshold}</span>
            </div>
            <p style={{ margin: "1px 0 0", fontSize: 9, color: T.textMuted }}>
              {item.shortfall > 0 ? `need ${item.shortfall} more` : "at threshold"} · [{item.category}]
            </p>
          </div>
        ))}
      </div>
    </IntelPanel>
  );
}

function AfterDeliveryPanel({ results, loading }) {
  if (loading) return <IntelPanel title="After Delivery"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!results.length) return (
    <IntelPanel title="After Delivery" badge="no orders" badgeColor={T.textMuted}>
      <EmptyState msg="No active orders to simulate." />
    </IntelPanel>
  );
  const buildable = results.filter(r => r.becomes_buildable);
  return (
    <IntelPanel
      title="After Delivery"
      badge={buildable.length > 0 ? `${buildable.length} become buildable` : "no change"}
      badgeColor={buildable.length > 0 ? T.green : T.textMuted}
    >
      <div style={{ maxHeight: 200, overflowY: "auto" }}>
        {results.map(r => (
          <div key={r.project_id} style={{
            padding: "4px 0", borderBottom: `1px solid ${T.border}22`,
            fontSize: 10, fontFamily: "JetBrains Mono, monospace",
            display: "flex", alignItems: "flex-start", gap: 6,
          }}>
            <span style={{ color: r.becomes_buildable ? T.green : T.orange, flexShrink: 0 }}>
              {r.becomes_buildable ? "✓" : "✗"}
            </span>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <span style={{ color: T.text, display: "block",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.project_name}
              </span>
              <span style={{ color: T.textMuted, fontSize: 9 }}>
                {r.becomes_buildable
                  ? "ready after delivery"
                  : `${r.still_missing.length} still missing`}
              </span>
            </div>
            <span style={{ fontSize: 9, color: T.textMuted, flexShrink: 0 }}>
              {r.current_readiness}%
            </span>
          </div>
        ))}
      </div>
    </IntelPanel>
  );
}

function DeliveriesPanel({ orders, loading }) {
  const delivered = orders.filter(o => o.status === "delivered").slice(0, 15);
  if (loading) return <IntelPanel title="Deliveries"><EmptyState msg="Loading…" /></IntelPanel>;
  if (!delivered.length) return (
    <IntelPanel title="Deliveries" badge="none" badgeColor={T.textMuted}>
      <EmptyState msg="No deliveries recorded yet." />
    </IntelPanel>
  );
  return (
    <IntelPanel title="Deliveries" badge={`${delivered.length} received`} badgeColor={T.green}>
      <div style={{ maxHeight: 200, overflowY: "auto" }}>
        {delivered.map(o => (
          <div key={o.id} style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "4px 0", borderBottom: `1px solid ${T.border}22`,
            fontSize: 10, fontFamily: "JetBrains Mono, monospace",
          }}>
            <span style={{ color: T.green, flexShrink: 0 }}>✓</span>
            <span style={{ flex: 1, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {o.part_name}
            </span>
            <span style={{ color: T.gold, flexShrink: 0 }}>×{o.quantity}</span>
            {o.vendor && <span style={{ color: T.textMuted, fontSize: 9, flexShrink: 0 }}>{o.vendor}</span>}
          </div>
        ))}
      </div>
    </IntelPanel>
  );
}

function ProcurementSection({ orders, lowStock, afterDelivery, loading, onReceiveOrder }) {
  const [collapsed, setCollapsed] = useState(false);
  const activeCount = orders.filter(o => !["delivered", "cancelled"].includes(o.status)).length;
  const lowStockCount = lowStock.length;

  return (
    <div style={{ borderTop: `1px solid ${T.border}`, background: "#060e1a", flexShrink: 0 }}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          display: "flex", alignItems: "center", gap: 12, padding: "8px 20px",
          cursor: "pointer", userSelect: "none",
        }}
      >
        <span style={{ fontSize: 10, color: T.gold, fontFamily: "JetBrains Mono, monospace",
          letterSpacing: "0.15em", textTransform: "uppercase" }}>
          {collapsed ? "▸" : "▾"} Procurement
        </span>
        {activeCount > 0 && (
          <span style={{ fontSize: 9, color: T.orange, border: `1px solid ${T.orange}44`,
            borderRadius: 10, padding: "0 6px", fontFamily: "JetBrains Mono, monospace" }}>
            {activeCount} active orders
          </span>
        )}
        {lowStockCount > 0 && (
          <span style={{ fontSize: 9, color: T.red, border: `1px solid ${T.red}44`,
            borderRadius: 10, padding: "0 6px", fontFamily: "JetBrains Mono, monospace" }}>
            {lowStockCount} low stock
          </span>
        )}
      </div>
      {!collapsed && (
        <div style={{ display: "flex", gap: 12, padding: "0 16px 16px" }}>
          <ActiveOrdersPanel orders={orders} onReceive={onReceiveOrder} loading={loading} />
          <DeliveriesPanel orders={orders} loading={loading} />
          <LowStockPanel items={lowStock} loading={loading} />
          <AfterDeliveryPanel results={afterDelivery} loading={loading} />
        </div>
      )}
    </div>
  );
}

// ── Summary Bar ───────────────────────────────────────────────────────────────

function SummaryBar({ summary }) {
  if (!summary) return null;
  const items = [
    { label: "Part Types", value: summary.total_parts ?? "—" },
    { label: "Units in Stock", value: summary.total_qty ?? "—" },
    { label: "Projects", value: summary.projects ?? "—" },
    { label: "Active", value: summary.active_projects ?? "—" },
    { label: "Pending Orders", value: summary.pending_orders ?? "—" },
  ];
  return (
    <div style={{
      display: "flex", gap: 0,
      borderBottom: `1px solid ${T.border}`,
    }}>
      {items.map((item, i) => (
        <div key={i} style={{
          flex: 1, padding: "8px 16px",
          borderRight: i < items.length - 1 ? `1px solid ${T.border}` : "none",
        }}>
          <p style={{ margin: 0, fontSize: 9, color: T.textMuted,
            fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase",
            letterSpacing: "0.1em" }}>
            {item.label}
          </p>
          <p style={{ margin: "2px 0 0", fontSize: 22, fontFamily: "JetBrains Mono, monospace",
            color: T.gold, fontWeight: 700, lineHeight: 1 }}>
            {item.value}
          </p>
        </div>
      ))}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function HardwareBoardPage() {
  const [summary, setSummary]   = useState(null);
  const [parts, setParts]       = useState([]);
  const [cats, setCats]         = useState([]);
  const [projects, setProjects] = useState([]);
  const [orders, setOrders]     = useState([]);
  const [imports, setImports]   = useState([]);
  const [search, setSearch]     = useState("");
  const [loading, setLoading]   = useState(true);

  // Phase 12B intelligence state
  const [readiness, setReadiness]         = useState([]);
  const [missingParts, setMissingParts]   = useState([]);
  const [recommendations, setRecs]        = useState([]);
  const [priorities, setPriorities]       = useState([]);
  const [intelLoading, setIntelLoading]   = useState(true);

  // Phase 12E procurement state
  const [lowStock, setLowStock]             = useState([]);
  const [afterDelivery, setAfterDelivery]   = useState([]);
  const [procLoading, setProcLoading]       = useState(true);

  const [modal, setModal] = useState(null); // {type, prefill}
  const [importDraft, setImportDraft] = useState(null);
  const [importing, setImporting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, p, proj, ord, imp] = await Promise.all([
        fetchHardwareSummary(),
        fetchHardwareInventory(),
        fetchHardwareProjects(),
        fetchHardwareOrders(),
        fetchHardwareImports(),
      ]);
      setSummary(s);
      setParts(p);
      setCats(s.categories || []);
      setProjects(proj);
      setOrders(ord);
      setImports(imp);
    } catch (e) {
      console.error("Hardware load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadIntel = useCallback(async () => {
    try {
      const [r, m, recs, pri] = await Promise.all([
        fetchHardwareReadiness(),
        fetchHardwareMissingParts(),
        fetchHardwareRecommendations(),
        fetchHardwarePriority(),
      ]);
      setReadiness(r);
      setMissingParts(m);
      setRecs(recs);
      setPriorities(pri);
    } catch (e) {
      console.error("Intelligence load failed:", e);
    } finally {
      setIntelLoading(false);
    }
  }, []);

  const loadProc = useCallback(async () => {
    try {
      const [ls, ad] = await Promise.all([
        fetchHardwareLowStock(),
        fetchHardwareAfterDelivery(),
      ]);
      setLowStock(ls);
      setAfterDelivery(ad);
    } catch (e) {
      console.error("Procurement load failed:", e);
    } finally {
      setProcLoading(false);
    }
  }, []);

  useEffect(() => {
    load(); loadIntel(); loadProc();
  }, [load, loadIntel, loadProc]);

  // ── Modal handlers ──────────────────────────────────────────────────────────

  async function refresh() { await Promise.all([load(), loadIntel(), loadProc()]); }

  async function handleAddPart(data) {
    await createHardwarePart(data);
    await refresh();
  }
  async function handleEditPart(part, data) {
    await updateHardwarePart(part.id, data);
    await refresh();
  }
  async function handleDeletePart(part) {
    if (!confirm(`Delete ${part.name}?`)) return;
    await deleteHardwarePart(part.id);
    await refresh();
  }

  async function handleAddProject(data) {
    await createHardwareProject(data);
    await refresh();
  }
  async function handleEditProject(project, data) {
    await updateHardwareProject(project.id, data);
    await refresh();
  }
  async function handleDeleteProject(project) {
    if (!confirm(`Delete project "${project.name}"? This will unassign all parts.`)) return;
    await deleteHardwareProject(project.id);
    await refresh();
  }

  async function handleAddOrder(data) {
    await createHardwareOrder(data);
    await refresh();
  }
  async function handleDeleteOrder(order) {
    if (!confirm(`Delete order for ${order.part_name}?`)) return;
    await deleteHardwareOrder(order.id);
    await refresh();
  }
  async function handleReceiveOrder(order) {
    if (!confirm(`Mark ${order.part_name} ×${order.quantity} as delivered and update inventory?`)) return;
    await receiveHardwareOrder(order.id);
    await refresh();
  }

  async function handleImportFileSelected(file, sourceType) {
    const preview = await createImportPreview(file, sourceType);
    setImportDraft(preview);
  }

  async function handleCommitImport() {
    if (!importDraft || importDraft.error) return;
    setImporting(true);
    try {
      await importHardwareFile(importDraft.fileName, importDraft.sourceType, importDraft.project || "");
      setImportDraft(null);
      await refresh();
    } catch (error) {
      setImportDraft({
        ...importDraft,
        error: error?.message || "Import failed. Make sure this file is in an indexed trusted location.",
      });
    } finally {
      setImporting(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh", background: T.bg,
      color: T.text, fontFamily: "system-ui, sans-serif",
      display: "flex", flexDirection: "column",
    }}>
      {/* ── Header ── */}
      <header style={{
        borderBottom: `1px solid ${T.border}`,
        padding: "10px 20px",
        display: "flex", alignItems: "center", gap: 16,
        background: T.surface, flexShrink: 0,
      }}>
        <Link to="/" style={{
          fontSize: 10, color: T.goldDim, textDecoration: "none",
          border: `1px solid ${T.border}`, borderRadius: 3,
          padding: "3px 10px", fontFamily: "JetBrains Mono, monospace",
          letterSpacing: "0.05em",
        }}>
          ← SILVIA
        </Link>
        <div>
          <p style={{ margin: 0, fontSize: 9, color: T.textMuted,
            fontFamily: "JetBrains Mono, monospace", letterSpacing: "0.15em",
            textTransform: "uppercase" }}>
            SILVIA / Hardware Operations Center
          </p>
          <h1 style={{ margin: 0, fontSize: 18, color: T.gold,
            fontFamily: "JetBrains Mono, monospace", fontWeight: 700,
            letterSpacing: "0.05em" }}>
            HARDWARE OPS
          </h1>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
          {loading && (
            <span style={{ fontSize: 10, color: T.textMuted,
              fontFamily: "JetBrains Mono, monospace", animation: "pulse 1s infinite" }}>
              Loading…
            </span>
          )}
          <button onClick={refresh} style={{
            background: "none", border: `1px solid ${T.border}`,
            color: T.textMuted, fontSize: 10, padding: "3px 10px",
            borderRadius: 3, cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
          }}>
            ↻ Refresh
          </button>
        </div>
      </header>

      {/* ── Summary bar ── */}
      <SummaryBar summary={summary} />

      {/* ── Three-column body ── */}
      <div style={{
        flex: 1, display: "grid",
        gridTemplateColumns: "1fr 1fr 320px",
        gap: 0,
        overflow: "hidden",
        minHeight: 0,
      }}>
        {/* Inventory */}
        <div style={{ padding: 16, borderRight: `1px solid ${T.border}`, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <InventoryPanel
            parts={parts}
            cats={cats}
            search={search}
            onSearch={setSearch}
            onAdd={() => setModal({ type: "addPart" })}
            onEdit={(p) => setModal({ type: "editPart", prefill: p })}
            onDelete={handleDeletePart}
          />
        </div>

        {/* Projects */}
        <div style={{ padding: 16, borderRight: `1px solid ${T.border}`, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <ProjectsPanel
            projects={projects}
            allParts={parts}
            onAdd={() => setModal({ type: "addProject" })}
            onEdit={(p) => setModal({ type: "editProject", prefill: p })}
            onDelete={handleDeleteProject}
            onRefresh={refresh}
          />
        </div>

        {/* Orders */}
        <div style={{ padding: 16, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <HardwareAssistantPanel onCommitted={refresh} />
          <ImportsPanel
            imports={imports}
            onFileSelected={handleImportFileSelected}
          />
          <OrdersPanel
            orders={orders}
            onAdd={() => setModal({ type: "addOrder" })}
            onDelete={handleDeleteOrder}
            onRefresh={refresh}
          />
        </div>
      </div>

      {/* ── Project Intelligence ── */}
      <IntelligenceSection
        readiness={readiness}
        missingParts={missingParts}
        recommendations={recommendations}
        priorities={priorities}
        loading={intelLoading}
      />

      {/* ── Procurement ── */}
      <ProcurementSection
        orders={orders}
        lowStock={lowStock}
        afterDelivery={afterDelivery}
        loading={procLoading}
        onReceiveOrder={handleReceiveOrder}
      />

      {/* ── Modals ── */}
      {modal?.type === "addPart" && (
        <AddPartModal onClose={() => setModal(null)} onSave={handleAddPart} />
      )}
      {modal?.type === "editPart" && (
        <AddPartModal
          onClose={() => setModal(null)}
          prefill={modal.prefill}
          onSave={(data) => handleEditPart(modal.prefill, data)}
        />
      )}
      {modal?.type === "addProject" && (
        <AddProjectModal onClose={() => setModal(null)} onSave={handleAddProject} />
      )}
      {modal?.type === "editProject" && (
        <AddProjectModal
          onClose={() => setModal(null)}
          prefill={modal.prefill}
          onSave={(data) => handleEditProject(modal.prefill, data)}
        />
      )}
      {modal?.type === "addOrder" && (
        <AddOrderModal onClose={() => setModal(null)} onSave={handleAddOrder} />
      )}
      {importDraft && (
        <ImportPreviewModal
          draft={importDraft}
          onChange={setImportDraft}
          onCancel={() => setImportDraft(null)}
          onCommit={handleCommitImport}
          committing={importing}
        />
      )}
    </div>
  );
}
