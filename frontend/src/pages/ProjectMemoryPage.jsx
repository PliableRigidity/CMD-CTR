import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchProjectMemory, fetchProjectTimeline, fetchMemoryProjects,
  searchMemory, recordMemory, importBrain63Memory,
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

const TYPE_META = {
  decision:        { icon: "◈", label: "Decision",        color: "#00e5ff" },
  lesson:          { icon: "◉", label: "Lesson Learned",  color: "#00ff88" },
  milestone:       { icon: "◆", label: "Milestone",       color: "#f5a623" },
  failure:         { icon: "✗", label: "Failure",         color: "#ff3b3b" },
  success:         { icon: "✓", label: "Success",         color: "#00ff88" },
  experiment:      { icon: "⊙", label: "Experiment",      color: "#a78bfa" },
  design_note:     { icon: "◇", label: "Design Note",     color: "#8b5cf6" },
  engineering_note:{ icon: "◎", label: "Engineering Note",color: "#60a5fa" },
  risk:            { icon: "⚠", label: "Risk",            color: "#fbbf24" },
  assumption:      { icon: "~", label: "Assumption",      color: "#6b7280" },
  retrospective:   { icon: "↺", label: "Retrospective",   color: "#f472b6" },
};

const TYPE_ORDER = [
  "milestone","decision","lesson","failure","success",
  "risk","experiment","design_note","engineering_note","assumption","retrospective",
];

function TypeBadge({ type }) {
  const m = TYPE_META[type] || { icon: "·", label: type, color: "#6b7280" };
  return (
    <span style={{
      fontSize: "0.65rem", fontFamily: "JetBrains Mono, monospace",
      color: m.color, border: `1px solid ${m.color}40`,
      borderRadius: 3, padding: "1px 5px", whiteSpace: "nowrap",
    }}>
      {m.icon} {m.label}
    </span>
  );
}

function MemoryCard({ entry, onDelete }) {
  const m = TYPE_META[entry.type] || { icon: "·", label: entry.type, color: "#6b7280" };
  return (
    <div style={{
      background: T.surfaceHi, border: `1px solid ${m.color}28`,
      borderLeft: `3px solid ${m.color}`, borderRadius: 6,
      padding: "10px 14px", marginBottom: 8,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span style={{ color: m.color, fontSize: "1rem", flexShrink: 0, marginTop: 1 }}>{m.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ color: T.text, fontWeight: 600, fontSize: "0.875rem" }}>{entry.title}</span>
            <TypeBadge type={entry.type} />
          </div>
          {entry.summary && entry.summary !== entry.title && (
            <div style={{ color: T.textMuted, fontSize: "0.8rem", marginTop: 4 }}>{entry.summary}</div>
          )}
          {entry.reasoning && (
            <div style={{ color: T.textMuted, fontSize: "0.78rem", marginTop: 3, fontStyle: "italic" }}>
              Reason: {entry.reasoning}
            </div>
          )}
          <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: "0.72rem", color: T.textMuted }}>
            <span>{entry.date}</span>
            <span style={{ color: T.goldDim }}>{entry.project}</span>
            {entry.source !== "manual" && <span style={{ opacity: 0.6 }}>{entry.source}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function TimelineView({ entries, project }) {
  if (!entries.length) {
    return (
      <div style={{ color: T.textMuted, textAlign: "center", padding: "40px 0" }}>
        No history recorded for <strong style={{ color: T.gold }}>{project}</strong> yet.
      </div>
    );
  }

  const grouped = {};
  entries.forEach(e => {
    const ym = (e.date || "").slice(0, 7) || "Unknown";
    if (!grouped[ym]) grouped[ym] = [];
    grouped[ym].push(e);
  });

  return (
    <div style={{ position: "relative" }}>
      <div style={{
        position: "absolute", left: 23, top: 0, bottom: 0,
        width: 1, background: `${T.gold}20`,
      }} />
      {Object.entries(grouped).map(([ym, items]) => (
        <div key={ym} style={{ marginBottom: 20 }}>
          <div style={{
            fontSize: "0.75rem", fontFamily: "JetBrains Mono, monospace",
            color: T.goldDim, marginBottom: 8, marginLeft: 46,
          }}>
            {ym}
          </div>
          {items.map((e, i) => {
            const m = TYPE_META[e.type] || { icon: "·", color: T.textMuted };
            return (
              <div key={e.id || i} style={{ display: "flex", gap: 14, marginBottom: 10 }}>
                <div style={{
                  width: 16, height: 16, borderRadius: "50%", flexShrink: 0,
                  background: m.color, marginTop: 3, zIndex: 1,
                  boxShadow: `0 0 6px ${m.color}60`,
                  marginLeft: 16,
                }} />
                <div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ color: T.text, fontWeight: 600, fontSize: "0.85rem" }}>{e.title}</span>
                    <TypeBadge type={e.type} />
                  </div>
                  {e.summary && e.summary !== e.title && (
                    <div style={{ color: T.textMuted, fontSize: "0.78rem", marginTop: 2 }}>{e.summary}</div>
                  )}
                  <div style={{ fontSize: "0.72rem", color: T.textMuted, marginTop: 2 }}>{e.date}</div>
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function RecordForm({ onSaved }) {
  const [type, setType] = useState("decision");
  const [project, setProject] = useState("");
  const [title, setTitle] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const handleSave = async () => {
    if (!title.trim()) { setErr("Title required"); return; }
    setSaving(true); setErr("");
    try {
      await recordMemory({ project: project || "General", type, title, reasoning });
      setTitle(""); setReasoning(""); setErr("");
      onSaved?.();
    } catch (e) {
      setErr(e.message || "Failed");
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    background: T.surface, border: `1px solid ${T.border}`,
    color: T.text, borderRadius: 4, padding: "7px 10px",
    fontFamily: "JetBrains Mono, monospace", fontSize: "0.82rem",
    outline: "none", width: "100%", boxSizing: "border-box",
  };
  const labelStyle = { color: T.textMuted, fontSize: "0.72rem", marginBottom: 4, display: "block" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Type</label>
          <select value={type} onChange={e => setType(e.target.value)} style={inputStyle}>
            {TYPE_ORDER.map(t => (
              <option key={t} value={t}>{TYPE_META[t]?.label || t}</option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Project</label>
          <input
            value={project} onChange={e => setProject(e.target.value)}
            placeholder="e.g. Cyberdeck"
            style={inputStyle}
          />
        </div>
      </div>
      <div>
        <label style={labelStyle}>Title / Description *</label>
        <input
          value={title} onChange={e => setTitle(e.target.value)}
          placeholder="e.g. Use PiSugar for power management"
          style={inputStyle}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSave()}
        />
      </div>
      <div>
        <label style={labelStyle}>Reasoning (optional)</label>
        <input
          value={reasoning} onChange={e => setReasoning(e.target.value)}
          placeholder="Why was this decision made?"
          style={inputStyle}
        />
      </div>
      {err && <div style={{ color: T.danger, fontSize: "0.8rem" }}>{err}</div>}
      <button
        onClick={handleSave} disabled={saving}
        style={{
          background: T.gold, color: "#000", border: "none", borderRadius: 4,
          padding: "8px 16px", fontWeight: 700, cursor: saving ? "not-allowed" : "pointer",
          fontFamily: "JetBrains Mono, monospace", opacity: saving ? 0.6 : 1,
        }}
      >
        {saving ? "Saving…" : "Record Memory"}
      </button>
    </div>
  );
}

export default function ProjectMemoryPage() {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [activeType, setActiveType] = useState("all");
  const [view, setView] = useState("board"); // board | timeline | search | record
  const [memories, setMemories] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState("");
  const [counts, setCounts] = useState({});
  const [showRecord, setShowRecord] = useState(false);

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchProjectMemory(selectedProject || "");
      setMemories(res.data || []);
      setCounts(res.by_type || {});
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  const loadTimeline = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await fetchProjectTimeline(selectedProject);
      setTimeline(res.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [selectedProject]);

  useEffect(() => {
    fetchMemoryProjects().then(r => setProjects(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (view === "board") loadMemories();
    if (view === "timeline" && selectedProject) loadTimeline();
  }, [view, selectedProject, loadMemories, loadTimeline]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    try {
      const res = await searchMemory(searchQuery, selectedProject || "");
      setSearchResults(res.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    setImporting(true); setImportMsg("");
    try {
      const res = await importBrain63Memory(selectedProject || "");
      if (res.ok) {
        setImportMsg(`Imported ${res.imported} memories from Brain63.`);
        loadMemories();
      } else {
        setImportMsg(res.error || "Import failed");
      }
    } catch (e) {
      setImportMsg("Import failed: " + (e.message || ""));
    } finally {
      setImporting(false);
    }
  };

  const filtered = memories.filter(m =>
    activeType === "all" || m.type === activeType
  );

  const totalCount = memories.length;

  return (
    <div style={{
      minHeight: "100vh", background: T.bg, color: T.text,
      fontFamily: "Inter, sans-serif", display: "flex", flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{
        background: T.surface, borderBottom: `1px solid ${T.border}`,
        padding: "14px 24px", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <div>
          <div style={{ fontSize: "0.65rem", color: T.textMuted, fontFamily: "JetBrains Mono, monospace", letterSpacing: "0.1em" }}>
            SILVIA / ENGINEERING MEMORY
          </div>
          <div style={{ fontSize: "1.3rem", fontWeight: 700, color: T.gold, letterSpacing: "0.04em" }}>
            Project Memory
          </div>
        </div>

        {/* Project picker */}
        <select
          value={selectedProject}
          onChange={e => { setSelectedProject(e.target.value); setActiveType("all"); }}
          style={{
            background: T.surface, border: `1px solid ${T.border}`, color: T.text,
            borderRadius: 4, padding: "6px 10px", fontFamily: "JetBrains Mono, monospace",
            fontSize: "0.82rem",
          }}
        >
          <option value="">All Projects</option>
          {projects.map(p => <option key={p} value={p}>{p}</option>)}
        </select>

        {/* View tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {[
            { id: "board", label: "Board" },
            { id: "timeline", label: "Timeline" },
            { id: "search", label: "Search" },
            { id: "record", label: "+ Record" },
          ].map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setView(id)}
              style={{
                background: view === id ? T.gold : "transparent",
                color: view === id ? "#000" : T.textMuted,
                border: `1px solid ${view === id ? T.gold : T.border}`,
                borderRadius: 4, padding: "5px 12px", cursor: "pointer",
                fontSize: "0.78rem", fontFamily: "JetBrains Mono, monospace",
                fontWeight: view === id ? 700 : 400,
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Import button */}
        <button
          onClick={handleImport} disabled={importing}
          title="Import memories from Brain63 vault (Decisions.md, Lessons_Learned.md, etc.)"
          style={{
            marginLeft: "auto", background: "transparent", color: T.goldDim,
            border: `1px solid ${T.border}`, borderRadius: 4, padding: "5px 12px",
            cursor: importing ? "not-allowed" : "pointer", fontSize: "0.75rem",
            fontFamily: "JetBrains Mono, monospace",
          }}
        >
          {importing ? "Importing…" : "⟳ Brain63"}
        </button>

        <Link to="/" style={{ color: T.textMuted, fontSize: "0.75rem", textDecoration: "none" }}>
          ← Command Center
        </Link>
      </div>

      {importMsg && (
        <div style={{
          background: "#0a1a0a", borderBottom: `1px solid ${T.success}40`,
          padding: "8px 24px", color: T.success, fontSize: "0.8rem",
        }}>
          {importMsg}
        </div>
      )}

      <div style={{ flex: 1, padding: "20px 24px", maxWidth: 1100, margin: "0 auto", width: "100%", boxSizing: "border-box" }}>

        {/* ── Board view ─────────────────────────────────── */}
        {view === "board" && (
          <div>
            {/* Type filter tabs */}
            <div style={{ display: "flex", gap: 6, marginBottom: 20, flexWrap: "wrap" }}>
              <button
                onClick={() => setActiveType("all")}
                style={typeTabStyle(activeType === "all")}
              >
                All {totalCount > 0 ? `(${totalCount})` : ""}
              </button>
              {TYPE_ORDER.filter(t => counts[t] > 0 || memories.some(m => m.type === t)).map(t => {
                const m = TYPE_META[t];
                return (
                  <button
                    key={t}
                    onClick={() => setActiveType(t)}
                    style={typeTabStyle(activeType === t, m.color)}
                  >
                    {m.icon} {m.label}s {counts[t] ? `(${counts[t]})` : ""}
                  </button>
                );
              })}
            </div>

            {loading ? (
              <div style={{ color: T.textMuted, textAlign: "center", padding: 40 }}>Loading…</div>
            ) : filtered.length === 0 ? (
              <div style={{ color: T.textMuted, textAlign: "center", padding: 40 }}>
                {memories.length === 0
                  ? 'No memories recorded yet. Use "record decision: ..." in the chat, or click "+ Record" above.'
                  : `No ${activeType}s found.`}
              </div>
            ) : (
              <div>
                {filtered.map((e, i) => <MemoryCard key={e.id || i} entry={e} />)}
              </div>
            )}
          </div>
        )}

        {/* ── Timeline view ──────────────────────────────── */}
        {view === "timeline" && (
          <div>
            {!selectedProject ? (
              <div style={{ color: T.textMuted, textAlign: "center", padding: 40 }}>
                Select a project to view its timeline.
              </div>
            ) : loading ? (
              <div style={{ color: T.textMuted, textAlign: "center", padding: 40 }}>Loading…</div>
            ) : (
              <TimelineView entries={timeline} project={selectedProject} />
            )}
          </div>
        )}

        {/* ── Search view ────────────────────────────────── */}
        {view === "search" && (
          <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                placeholder='Search memories… e.g. "Arch Linux", "ESP32", "power system"'
                style={{
                  flex: 1, background: T.surface, border: `1px solid ${T.border}`,
                  color: T.text, borderRadius: 4, padding: "9px 12px",
                  fontFamily: "JetBrains Mono, monospace", fontSize: "0.85rem", outline: "none",
                }}
              />
              <button
                onClick={handleSearch} disabled={loading}
                style={{
                  background: T.gold, color: "#000", border: "none", borderRadius: 4,
                  padding: "9px 18px", cursor: "pointer", fontWeight: 700, fontSize: "0.82rem",
                }}
              >
                {loading ? "…" : "Search"}
              </button>
            </div>
            {searchResults.length > 0 && (
              <div>
                <div style={{ color: T.textMuted, fontSize: "0.78rem", marginBottom: 12 }}>
                  {searchResults.length} result(s)
                </div>
                {searchResults.map((e, i) => <MemoryCard key={e.id || i} entry={e} />)}
              </div>
            )}
            {searchQuery && searchResults.length === 0 && !loading && (
              <div style={{ color: T.textMuted, textAlign: "center", padding: 40 }}>
                No memories found for "{searchQuery}".
              </div>
            )}
          </div>
        )}

        {/* ── Record view ────────────────────────────────── */}
        {view === "record" && (
          <div style={{ maxWidth: 560 }}>
            <div style={{ color: T.gold, fontWeight: 700, marginBottom: 16 }}>Record Engineering Memory</div>
            <RecordForm onSaved={() => { setView("board"); loadMemories(); }} />
          </div>
        )}
      </div>

      {/* Stats bar */}
      <div style={{
        background: T.surface, borderTop: `1px solid ${T.border}`,
        padding: "10px 24px", display: "flex", gap: 20,
        fontSize: "0.72rem", color: T.textMuted, fontFamily: "JetBrains Mono, monospace",
        flexWrap: "wrap",
      }}>
        {Object.entries(counts).map(([t, c]) => {
          const m = TYPE_META[t] || { icon: "·", label: t, color: T.textMuted };
          return (
            <span key={t} style={{ color: m.color }}>
              {m.icon} {c} {m.label}s
            </span>
          );
        })}
        {Object.keys(counts).length === 0 && <span>No memories yet</span>}
        <span style={{ marginLeft: "auto", color: T.goldDim }}>
          {projects.length} project(s) with memory
        </span>
      </div>
    </div>
  );
}

function typeTabStyle(active, color) {
  return {
    background: active ? (color || T.gold) : "transparent",
    color: active ? "#000" : (color || T.textMuted),
    border: `1px solid ${active ? (color || T.gold) : "rgba(201,148,58,0.18)"}`,
    borderRadius: 4, padding: "4px 10px", cursor: "pointer",
    fontSize: "0.74rem", fontFamily: "JetBrains Mono, monospace",
    fontWeight: active ? 700 : 400, transition: "all 0.15s",
  };
}
