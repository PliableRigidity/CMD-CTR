export default function DevicesPanel({ devices, audio }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Node Fabric / Infrastructure</p>
          <h2>Connected Nodes</h2>
        </div>
      </div>

      <div className="node-list">
        <div className="node-row">
          <span className={`node-dot node-dot--${audio?.available ? "online" : "offline"}`} />
          <span className="node-name">Workstation</span>
          <span className="node-meta">
            {audio?.available ? `Audio · Vol ${audio.volume_percent ?? "?"}%` : "Audio offline"}
          </span>
          <span className={`node-status node-status--${audio?.available ? "online" : "offline"}`}>
            {audio?.available ? "LIVE" : "OFF"}
          </span>
        </div>

        {devices.map((device) => (
          <div className="node-row" key={device.id}>
            <span className={`node-dot node-dot--${device.status}`} />
            <span className="node-name">{device.name}</span>
            <span className="node-meta">{device.type} · {device.location}</span>
            <span className={`node-status node-status--${device.status}`}>
              {device.status.toUpperCase()}
            </span>
          </div>
        ))}

        {devices.length === 0 && (
          <p className="muted" style={{ fontSize: "0.73rem", padding: "4px 0" }}>
            No additional nodes registered.
          </p>
        )}
      </div>
    </section>
  );
}
