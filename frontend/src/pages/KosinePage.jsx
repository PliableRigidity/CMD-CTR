import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchKosineStatus, kosineMigratePreview, kosineMigrate,
  fetchKosineBackups, kosineRestore, fetchKosineAudit,
  kosineMaintenanceScan, kosineMaintenanceRun,
  fetchKosineSuggestions, kosineApplySuggestion,
  kosineSubmitSuggestion, kosineApproveSuggestion, kosineRejectSuggestion,
} from "../lib/api";

const T = {
  bg: "#060b14", surface: "#0d1623", surfaceHi: "#111e2e",
  border: "rgba(201,148,58,0.18)", borderHi: "rgba(201,148,58,0.45)",
  gold: "#c9943a", goldDim: "#8a6422", text: "#ddd5c5", textMuted: "#6b7280",
  success: "#00ff88", danger: "#ff3b3b", info: "#60a5fa", warning: "#fbbf24",
};

function Panel({ title, children, accent }) {
  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`, borderRadius: 6,
      padding: "14px 16px", marginBottom: 12,
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

function Pill({ on, label }) {
  return (
    <span style={{
      fontSize: "0.62rem", fontFamily: "JetBrains Mono, monospace", padding: "2px 8px",
      borderRadius: 10, marginRight: 6,
      background: on ? "rgba(0,255,136,0.12)" : "rgba(107,114,128,0.15)",
      color: on ? T.success : T.textMuted,
      border: `1px solid ${on ? "rgba(0,255,136,0.35)" : "rgba(107,114,128,0.3)"}`,
    }}>{label}: {on ? "ON" : "OFF"}</span>
  );
}

const STATUS_COLOR = {
  draft: T.textMuted, pending_review: T.info, approved: T.gold,
  executing: T.info, completed: T.success, failed: T.danger,
  rejected: T.danger, cancelled: T.textMuted,
};

function StatusBadge({ status }) {
  const c = STATUS_COLOR[status] || T.textMuted;
  return (
    <span style={{
      fontSize: "0.6rem", fontFamily: "JetBrains Mono, monospace", padding: "2px 8px",
      borderRadius: 10, background: `${c}22`, color: c, border: `1px solid ${c}55`,
      textTransform: "uppercase", letterSpacing: 0.5,
    }}>{(status || "?").replace("_", " ")}</span>
  );
}

function Btn({ onClick, children, tone = "gold", disabled, title }) {
  const c = tone === "danger" ? T.danger : tone === "info" ? T.info : tone === "success" ? T.success : T.gold;
  return (
    <button onClick={onClick} disabled={disabled} title={title} style={{
      background: "transparent", color: c, border: `1px solid ${c}66`,
      borderRadius: 4, padding: "5px 10px", fontSize: "0.68rem", cursor: disabled ? "not-allowed" : "pointer",
      fontFamily: "JetBrains Mono, monospace", marginRight: 6, marginTop: 4, opacity: disabled ? 0.4 : 1,
    }}>{children}</button>
  );
}

const SEV_COLOR = { warn: T.warning, info: T.info };

export default function KosinePage() {
  const [status, setStatus] = useState(null);
  const [preview, setPreview] = useState(null);
  const [scan, setScan] = useState(null);
  const [audit, setAudit] = useState([]);
  const [backups, setBackups] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [sugResult, setSugResult] = useState({});   // code -> {kind, data}
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  const refresh = useCallback(async () => {
    try {
      const s = await fetchKosineStatus();
      setStatus(s);
      if (s.enabled) {
        const [a, b, sg] = await Promise.all([
          fetchKosineAudit(20), fetchKosineBackups(), fetchKosineSuggestions(50),
        ]);
        setAudit(a.records || []);
        setBackups(b.backups || []);
        setSuggestions(sg.suggestions || []);
      }
    } catch (e) { setMsg(String(e.message || e)); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const doPreview = async () => {
    setBusy("preview"); setMsg("");
    try { setPreview(await kosineMigratePreview()); }
    catch (e) { setMsg(String(e.message || e)); }
    finally { setBusy(""); }
  };
  const doMigrate = async () => {
    if (!window.confirm("Import Brain63 into KOSINE? A backup is taken first; this is reversible.")) return;
    setBusy("migrate"); setMsg("");
    try {
      const r = await kosineMigrate(true);
      setMsg(r.ok ? `Migrated: +${r.objects_created} objects, +${r.relationships_created} relationships.` : `Error: ${r.error}`);
      await refresh();
    } catch (e) { setMsg(String(e.message || e)); }
    finally { setBusy(""); }
  };
  const doScan = async () => {
    setBusy("scan"); setMsg("");
    try { setScan(await kosineMaintenanceScan(100)); }
    catch (e) { setMsg(String(e.message || e)); }
    finally { setBusy(""); }
  };
  const doDraft = async () => {
    setBusy("draft"); setMsg("");
    try {
      const r = await kosineMaintenanceRun(true);
      setScan(r);
      setMsg(r.autodraft_allowed
        ? `Drafted ${r.drafted_count} suggestion workflow(s) — review on the Workflow board.`
        : "Autodraft is disabled (set KOSINE_MAINTENANCE_AUTODRAFT=true). Scan-only.");
    } catch (e) { setMsg(String(e.message || e)); }
    finally { setBusy(""); }
  };

  // ── suggestion actions (state via WorkflowEngine; execution via /apply) ──────
  const runSug = async (code, kind, fn) => {
    setBusy(`${kind}:${code}`); setMsg("");
    try {
      const r = await fn();
      if (kind === "dryrun") {
        setSugResult((m) => ({ ...m, [code]: { kind: "dryrun", data: r } }));
      } else if (kind === "apply") {
        setSugResult((m) => ({ ...m, [code]: { kind: "apply", data: r } }));
        setMsg(r.ok ? `Applied ${code} → ${r.status}.` : `Apply ${code} failed: ${r.error}`);
      } else if (!r.ok && r.error) {
        setMsg(`${code}: ${r.error}`);
      }
      await refresh();
    } catch (e) { setMsg(String(e.message || e)); }
    finally { setBusy(""); }
  };
  const onSubmit  = (code) => runSug(code, "submit",  () => kosineSubmitSuggestion(code));
  const onApprove = (code) => runSug(code, "approve", () => kosineApproveSuggestion(code));
  const onReject  = (code) => runSug(code, "reject",  () => kosineRejectSuggestion(code));
  const onDryRun  = (code) => runSug(code, "dryrun",  () => kosineApplySuggestion(code, { dry_run: true }));
  const onApply   = (code) => {
    if (!window.confirm(`Apply ${code} to KOSINE? This performs a real, audited write.`)) return;
    return runSug(code, "apply", () => kosineApplySuggestion(code, { approve: true }));
  };

  const st = status || {};
  const writesOff = !st.writes_allowed;

  return (
    <div style={{ background: T.bg, minHeight: "100vh", color: T.text, padding: "20px 24px", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: "1.1rem", color: T.gold, margin: 0, fontFamily: "JetBrains Mono, monospace" }}>KOSINE MEMORY</h1>
          <div style={{ fontSize: "0.7rem", color: T.textMuted }}>Structured knowledge backend · Brain63 migration · autonomous maintenance</div>
        </div>
        <Link to="/" style={{ color: T.textMuted, fontSize: "0.75rem", textDecoration: "none" }}>← Command Center</Link>
      </div>

      {msg && (
        <div style={{ background: T.surfaceHi, border: `1px solid ${T.borderHi}`, borderRadius: 4, padding: "8px 12px", marginBottom: 12, fontSize: "0.75rem", color: T.text }}>{msg}</div>
      )}

      <Panel title="Status" accent={st.available ? T.success : T.danger}>
        {!st.enabled ? (
          <div style={{ fontSize: "0.8rem", color: T.warning }}>
            KOSINE is disabled. Set <code>KOSINE_ENABLED=true</code> in <code>.env</code> and restart the backend.
          </div>
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 12 }}>
              <Stat label="Objects" value={st.object_count ?? "—"} />
              <Stat label="Available" value={st.available ? "YES" : "NO"} color={st.available ? T.success : T.danger} />
              <Stat label="Mode" value={(st.mode || "").replace("_", "-")} color={T.info} />
              <Stat label="Audit rows" value={audit.length} />
            </div>
            <div>
              <Pill on={st.primary} label="PRIMARY" />
              <Pill on={st.writes_allowed} label="WRITES" />
              <Pill on={st.maintenance_autodraft} label="AUTODRAFT" />
            </div>
            <div style={{ fontSize: "0.62rem", color: T.textMuted, marginTop: 8, fontFamily: "JetBrains Mono, monospace" }}>
              priority: {(st.priority || []).join(" → ")}
            </div>
            <div style={{ fontSize: "0.62rem", color: T.textMuted, marginTop: 4, fontFamily: "JetBrains Mono, monospace" }}>
              db: {st.db_path}
            </div>
          </>
        )}
      </Panel>

      {st.enabled && (
        <>
          <Panel title="Brain63 → KOSINE Migration">
            <Btn onClick={doPreview} disabled={busy}>Preview (dry-run)</Btn>
            <Btn onClick={doMigrate} tone="info" disabled={busy}>Migrate now</Btn>
            {preview && (
              <div style={{ marginTop: 10, fontSize: "0.72rem", fontFamily: "JetBrains Mono, monospace", color: T.text }}>
                <div>files: {preview.files_scanned} · est. objects: {preview.objects_created} · relationships: {preview.relationships_created} · skipped: {preview.skipped_duplicates}</div>
                {preview.note && <div style={{ color: T.textMuted, marginTop: 4 }}>{preview.note}</div>}
              </div>
            )}
            {backups.length > 0 && (
              <div style={{ marginTop: 10, fontSize: "0.68rem", color: T.textMuted }}>
                {backups.length} backup(s) · latest: {backups[0]?.name || backups[0]?.path}
              </div>
            )}
          </Panel>

          <Panel title="Autonomous Maintenance (suggestions only)">
            <Btn onClick={doScan} disabled={busy}>Scan (read-only)</Btn>
            <Btn onClick={doDraft} tone="info" disabled={busy}>Draft suggestions</Btn>
            {scan && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: "0.72rem", color: T.text, marginBottom: 8, fontFamily: "JetBrains Mono, monospace" }}>
                  scanned {scan.scanned} · findings {scan.findings_count} · {Object.entries(scan.by_kind || {}).map(([k, v]) => `${k}:${v}`).join("  ")}
                </div>
                {(scan.findings || []).slice(0, 20).map((f, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: "0.7rem", padding: "3px 0", borderBottom: `1px solid ${T.border}` }}>
                    <span style={{ color: SEV_COLOR[f.severity] || T.textMuted, fontFamily: "JetBrains Mono, monospace", minWidth: 72 }}>{f.kind}</span>
                    <span style={{ color: T.textMuted, minWidth: 70 }}>{f.type}</span>
                    <span style={{ color: T.text }}>{f.title || f.object_id}</span>
                    <span style={{ color: T.textMuted, marginLeft: "auto" }}>{f.detail}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Suggestions (approval-gated apply)">
            {writesOff && (
              <div style={{ fontSize: "0.68rem", color: T.warning, marginBottom: 10 }}>
                Real apply is disabled — <code>KOSINE_ALLOW_WRITES=false</code>. Dry-run still works;
                set the flag and restart the backend to enable writes.
              </div>
            )}
            {suggestions.length === 0 ? (
              <div style={{ fontSize: "0.75rem", color: T.textMuted }}>
                No suggestions yet. Run “Draft suggestions” above (requires autodraft).
              </div>
            ) : suggestions.map((s) => {
              const status = s.status;
              const terminal = ["completed", "failed", "rejected", "cancelled"].includes(status);
              const isBusy = busy.endsWith(`:${s.code}`);
              const res = sugResult[s.code];
              return (
                <div key={s.code} style={{ padding: "8px 0", borderBottom: `1px solid ${T.border}` }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ color: T.gold, fontFamily: "JetBrains Mono, monospace", fontSize: "0.72rem", minWidth: 62 }}>{s.code}</span>
                    <StatusBadge status={status} />
                    <span style={{ color: T.text, fontSize: "0.74rem" }}>{s.title}</span>
                    <span style={{ color: T.textMuted, fontSize: "0.62rem", marginLeft: "auto", fontFamily: "JetBrains Mono, monospace" }}>
                      {s.tool_name}
                    </span>
                  </div>
                  {s.description && <div style={{ fontSize: "0.66rem", color: T.textMuted, marginTop: 3 }}>{s.description}</div>}

                  {!terminal && (
                    <div style={{ marginTop: 4 }}>
                      {status === "draft" && <Btn onClick={() => onSubmit(s.code)} disabled={isBusy}>Submit for review</Btn>}
                      {(status === "draft" || status === "pending_review") && (
                        <>
                          <Btn onClick={() => onApprove(s.code)} disabled={isBusy}>Approve</Btn>
                          <Btn onClick={() => onReject(s.code)} tone="danger" disabled={isBusy}>Reject</Btn>
                        </>
                      )}
                      {status === "approved" && <Btn onClick={() => onDryRun(s.code)} tone="info" disabled={isBusy}>Dry run apply</Btn>}
                      <Btn
                        onClick={() => onApply(s.code)}
                        tone="success"
                        disabled={isBusy || writesOff}
                        title={writesOff ? "KOSINE_ALLOW_WRITES=false" : "Approve then apply (real write)"}
                      >Approve &amp; apply</Btn>
                    </div>
                  )}

                  {res?.kind === "dryrun" && res.data?.ok && (
                    <div style={{ marginTop: 5, fontSize: "0.64rem", fontFamily: "JetBrains Mono, monospace", color: T.info, background: T.surfaceHi, borderRadius: 4, padding: "5px 8px" }}>
                      DRY-RUN — would call <b>{res.data.would_apply?.tool}</b>({JSON.stringify(res.data.would_apply?.args)})
                    </div>
                  )}
                  {res?.kind === "apply" && (
                    <div style={{ marginTop: 5, fontSize: "0.64rem", fontFamily: "JetBrains Mono, monospace", color: res.data?.ok ? T.success : T.danger, background: T.surfaceHi, borderRadius: 4, padding: "5px 8px" }}>
                      {res.data?.ok
                        ? `APPLIED → ${res.data.status} (see audit log below)`
                        : `FAILED — ${res.data?.error}`}
                    </div>
                  )}
                </div>
              );
            })}
          </Panel>

          <Panel title="Write Audit Log">
            {audit.length === 0 ? (
              <div style={{ fontSize: "0.75rem", color: T.textMuted }}>No writes recorded yet.</div>
            ) : audit.map((r, i) => (
              <div key={i} style={{ fontSize: "0.68rem", fontFamily: "JetBrains Mono, monospace", padding: "3px 0", borderBottom: `1px solid ${T.border}`, display: "flex", gap: 8 }}>
                <span style={{ color: r.status === "ok" ? T.success : T.danger, minWidth: 30 }}>{r.status}</span>
                <span style={{ color: T.gold, minWidth: 130 }}>{r.tool}</span>
                <span style={{ color: T.textMuted }}>{r.actor}</span>
                <span style={{ color: T.textMuted, marginLeft: "auto" }}>{(r.objects_changed || []).length} obj · {(r.events_created || []).length} evt</span>
              </div>
            ))}
          </Panel>
        </>
      )}
    </div>
  );
}
