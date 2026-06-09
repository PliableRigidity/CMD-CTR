export default function EventsStreamPanel({ logs }) {
  const recent = [...logs].reverse().slice(0, 5);

  return (
    <section className="panel">
      <div className="panel-heading" style={{ marginBottom: "10px" }}>
        <div>
          <p className="eyebrow">System Telemetry</p>
          <h2>Event Log</h2>
        </div>
        <span className="muted" style={{ fontSize: "0.68rem" }}>
          {logs.length} total
        </span>
      </div>

      <div className="log-strip">
        {recent.length ? (
          recent.map((log, i) => (
            <div
              className={`log-row log-row--${log.level || "info"}`}
              key={`${log.timestamp}-${i}`}
            >
              <span className="log-ts">
                {log.timestamp ? log.timestamp.slice(11, 19) : "--:--:--"}
              </span>
              <span className="log-title">{log.title}</span>
              <span className="log-detail">{log.detail}</span>
            </div>
          ))
        ) : (
          <p className="muted" style={{ fontSize: "0.73rem" }}>Waiting for events.</p>
        )}
      </div>
    </section>
  );
}
