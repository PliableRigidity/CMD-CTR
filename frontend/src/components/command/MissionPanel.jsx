export default function MissionPanel({ mode, route, onOpenIntel }) {
  return (
    <section className="panel mission-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Mission Context / Ops Layer</p>
          <h2>Operational Focus</h2>
        </div>
        <span className={`state-pill state-pill--${mode === "decision" ? "busy" : "idle"}`}>
          {mode === "decision" ? "Council Online" : "Direct Assist Online"}
        </span>
      </div>

      <div className="mission-grid">
        <article className="mission-card">
          <span className="module-id">CTX-01</span>
          <strong>Current Route</strong>
          <p>{route.destination ? `${route.origin} -> ${route.destination}` : "No active route"}</p>
          <p className="muted">
            {route.distance ? `${route.distance} | ${route.eta}` : "Request a route from the navigation panel."}
          </p>
        </article>

        <article className="mission-card">
          <span className="module-id">INT-02</span>
          <strong>Intel Board</strong>
          <p>Open the full world intelligence screen on a second monitor.</p>
          <button type="button" className="panel-button" onClick={onOpenIntel}>
            Open Intel Board
          </button>
        </article>
      </div>
    </section>
  );
}
