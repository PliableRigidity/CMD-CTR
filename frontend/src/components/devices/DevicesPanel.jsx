export default function DevicesPanel({ devices, audio }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Devices / Node Fabric</p>
          <h2>Connected Nodes</h2>
        </div>
      </div>

      <article className="device-card">
        <div className="device-card__head">
          <strong>Host Audio</strong>
          <span className={`device-state device-state--${audio?.available ? "online" : "standby"}`}>
            {audio?.available ? "ready" : "offline"}
          </span>
        </div>
        <p>{audio?.volume_percent != null ? `Volume ${audio.volume_percent}%` : "Volume state unavailable"}</p>
        <p className="muted">Backend: {audio?.backend || "unknown"}</p>
      </article>

      <div className="device-list">
        {devices.map((device) => (
          <article className="device-card" key={device.id}>
            <div className="device-card__head">
              <strong>{device.name}</strong>
              <span className={`device-state device-state--${device.status}`}>{device.status}</span>
            </div>
            <p>{device.type} | {device.location}</p>
            <p className="muted">{device.capabilities.join(" | ")}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
