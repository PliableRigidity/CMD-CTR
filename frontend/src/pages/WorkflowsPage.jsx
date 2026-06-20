import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchWorkflows, fetchPendingWorkflows, fetchWorkflowHistory,
  approveWorkflow, rejectWorkflow, cancelWorkflow,
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

const STATUS_COLORS = {
  draft:          T.textMuted,
  pending_review: T.warning,
  approved:       T.info,
  rejected:       T.danger,
  executing:      T.gold,
  completed:      T.success,
  failed:         T.danger,
  cancelled:      T.textMuted,
};

const RISK_COLORS = {
  read:     T.textMuted,
  low:      T.success,
  moderate: T.warning,
  high:     "#ff8c00",
  critical: T.danger,
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

function Badge({ text, color }) {
  return (
    <span style={{
      display: "inline-block", padding: "1px 8px", borderRadius: 3,
      fontSize: "0.65rem", fontFamily: "JetBrains Mono, monospace",
      background: `${color}22`, color, border: `1px solid ${color}44`,
      textTransform: "uppercase", letterSpacing: 0.5,
    }}>
      {text}
    </span>
  );
}

function WorkflowCard({ wf, onAction }) {
  const status = wf.status || "unknown";
  const statusColor = STATUS_COLORS[status] || T.textMuted;
  const riskColor = RISK_COLORS[wf.risk_level] || T.textMuted;
  const created = (wf.created_at || "").slice(0, 16).replace("T", " ");
  const isPending = status === "pending_review";

  return (
    <div style={{
      background: T.surfaceHi, border: `1px solid ${isPending ? T.borderHi : T.border}`,
      borderRadius: 5, padding: "12px 14px", marginBottom: 8,
      borderLeft: `3px solid ${statusColor}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.75rem", color: T.gold, fontWeight: 600 }}>
            {wf.code}
          </span>
          <Badge text={status.replace("_", " ")} color={statusColor} />
          <Badge text={wf.risk_level} color={riskColor} />
        </div>
        <span style={{ fontSize: "0.65rem", color: T.textMuted }}>{created}</span>
      </div>

      <div style={{ fontSize: "0.85rem", color: T.text, marginBottom: 4, fontWeight: 500 }}>
        {wf.title}
      </div>

      <div style={{ fontSize: "0.7rem", color: T.textMuted, marginBottom: 6 }}>
        {(wf.category || "").replace("_", " ")}
        {wf.project ? ` · ${wf.project}` : ""}
        {wf.tool_name ? ` · ${wf.tool_name}` : ""}
      </div>

      {wf.description && (
        <pre style={{
          fontSize: "0.7rem", color: T.textMuted, margin: "6px 0",
          whiteSpace: "pre-wrap", fontFamily: "JetBrains Mono, monospace",
          background: "#0a101c", padding: "6px 8px", borderRadius: 3,
          border: `1px solid ${T.border}`,
        }}>
          {wf.description}
        </pre>
      )}

      {wf.diff_text && (
        <pre style={{
          fontSize: "0.7rem", margin: "6px 0",
          whiteSpace: "pre-wrap", fontFamily: "JetBrains Mono, monospace",
          background: "#0a101c", padding: "6px 8px", borderRadius: 3,
          border: `1px solid ${T.border}`,
        }}>
          {wf.diff_text}
        </pre>
      )}

      {wf.execution_result && (
        <div style={{ fontSize: "0.7rem", color: status === "failed" ? T.danger : T.success, marginTop: 4 }}>
          Result: {wf.execution_result}
        </div>
      )}

      {isPending && (
        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <button
            onClick={() => onAction("approve", wf.code)}
            style={{
              background: `${T.success}22`, color: T.success,
              border: `1px solid ${T.success}44`, borderRadius: 4,
              padding: "4px 12px", fontSize: "0.7rem", cursor: "pointer",
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            Approve
          </button>
          <button
            onClick={() => onAction("reject", wf.code)}
            style={{
              background: `${T.danger}22`, color: T.danger,
              border: `1px solid ${T.danger}44`, borderRadius: 4,
              padding: "4px 12px", fontSize: "0.7rem", cursor: "pointer",
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            Reject
          </button>
          <button
            onClick={() => onAction("cancel", wf.code)}
            style={{
              background: `${T.textMuted}22`, color: T.textMuted,
              border: `1px solid ${T.textMuted}44`, borderRadius: 4,
              padding: "4px 12px", fontSize: "0.7rem", cursor: "pointer",
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

export default function WorkflowsPage() {
  const [view, setView] = useState("pending");
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      let data;
      if (view === "pending") data = await fetchPendingWorkflows();
      else if (view === "history") data = await fetchWorkflowHistory();
      else data = await fetchWorkflows();
      setWorkflows(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to load workflows:", e);
      setWorkflows([]);
    }
    setLoading(false);
  }, [view]);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (action, code) => {
    try {
      if (action === "approve") await approveWorkflow(code);
      else if (action === "reject") await rejectWorkflow(code);
      else if (action === "cancel") await cancelWorkflow(code);
      load();
    } catch (e) {
      console.error(`Workflow ${action} failed:`, e);
    }
  };

  const pending = workflows.filter(w => w.status === "pending_review");
  const completed = workflows.filter(w => w.status === "completed");
  const failed = workflows.filter(w => w.status === "failed");
  const rejected = workflows.filter(w => w.status === "rejected");

  return (
    <div style={{
      minHeight: "100vh", background: T.bg, color: T.text,
      fontFamily: "'Inter', -apple-system, sans-serif",
      padding: "20px 24px",
    }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <Link to="/" style={{ color: T.goldDim, textDecoration: "none", fontSize: "0.7rem" }}>
              SILVIA
            </Link>
            <h1 style={{ margin: "4px 0 0", fontSize: "1.2rem", fontWeight: 600, color: T.gold }}>
              Workflow Review Board
            </h1>
          </div>
          <button
            onClick={load}
            style={{
              background: T.surfaceHi, color: T.textMuted,
              border: `1px solid ${T.border}`, borderRadius: 4,
              padding: "6px 12px", fontSize: "0.7rem", cursor: "pointer",
            }}
          >
            Refresh
          </button>
        </div>

        {/* Stats */}
        <Panel title="Overview">
          <div style={{ display: "flex", justifyContent: "space-around" }}>
            <Stat label="Pending" value={view === "all" ? pending.length : "—"} color={T.warning} />
            <Stat label="Completed" value={view === "all" ? completed.length : "—"} color={T.success} />
            <Stat label="Failed" value={view === "all" ? failed.length : "—"} color={T.danger} />
            <Stat label="Rejected" value={view === "all" ? rejected.length : "—"} color={T.textMuted} />
            <Stat label="Total" value={workflows.length} />
          </div>
        </Panel>

        {/* View tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
          {["pending", "all", "history"].map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              style={{
                background: view === v ? `${T.gold}22` : "transparent",
                color: view === v ? T.gold : T.textMuted,
                border: `1px solid ${view === v ? T.borderHi : T.border}`,
                borderRadius: 4, padding: "5px 14px", fontSize: "0.7rem",
                cursor: "pointer", fontFamily: "JetBrains Mono, monospace",
                textTransform: "capitalize",
              }}
            >
              {v === "pending" ? "Pending Review" : v === "all" ? "All Workflows" : "History"}
            </button>
          ))}
        </div>

        {/* Workflow list */}
        {loading ? (
          <div style={{ color: T.textMuted, textAlign: "center", padding: 40, fontSize: "0.8rem" }}>
            Loading workflows…
          </div>
        ) : workflows.length === 0 ? (
          <Panel title={view === "pending" ? "Pending Review" : view === "history" ? "History" : "All Workflows"}>
            <div style={{ color: T.textMuted, fontSize: "0.8rem", textAlign: "center", padding: 20 }}>
              No workflows found.
            </div>
          </Panel>
        ) : (
          <div>
            {workflows.map(wf => (
              <WorkflowCard key={wf.id || wf.code} wf={wf} onAction={handleAction} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
