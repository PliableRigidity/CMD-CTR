export default function EventsStreamPanel({ logs }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Event Stream / System Telemetry</p>
          <h2>System Logs</h2>
        </div>
      </div>

      <div className="log-list">
        {logs.length ? (
          [...logs].reverse().map((log) => (
            <article className={`log-item log-item--${log.level || "info"}`} key={`${log.timestamp}-${log.title}-${log.detail}`}>
              <span>{log.timestamp}</span>
              <strong>{log.title}</strong>
              <p>{log.detail}</p>
            </article>
          ))
        ) : (
          <p className="muted">Waiting for live assistant events.</p>
        )}
      </div>
    </section>
  );
}
