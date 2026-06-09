const SEV_CLASS = { critical: "critical", warning: "warning", info: "info" };
const CAT_LABEL = {
  infra: "INFRA",
  intel: "INTEL",
  mission: "OPS",
  system: "SYS",
  security: "SEC",
};

export default function WatchOfficerPanel({ alerts = [], onDismiss }) {
  const activeCount = alerts.length;

  return (
    <section className="panel">
      <div className="panel-heading" style={{ marginBottom: "10px" }}>
        <div>
          <p className="eyebrow">Operations Context</p>
          <h2>Watch Officer</h2>
        </div>
        {activeCount > 0 && (
          <span className="watch-badge watch-badge--active">{activeCount}</span>
        )}
      </div>

      <div className="watch-list">
        {activeCount === 0 && (
          <p className="muted" style={{ fontSize: "0.73rem", padding: "4px 0" }}>
            All clear — no active alerts.
          </p>
        )}
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`watch-row watch-row--${SEV_CLASS[alert.severity] || "info"}`}
          >
            <span className={`watch-dot watch-dot--${SEV_CLASS[alert.severity] || "info"}`} />
            <span className="watch-cat">
              {CAT_LABEL[alert.category] || alert.category.toUpperCase()}
            </span>
            <span className="watch-msg">{alert.message}</span>
            <button
              className="watch-dismiss"
              onClick={() => onDismiss(alert.id)}
              title="Dismiss"
              aria-label="Dismiss alert"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
