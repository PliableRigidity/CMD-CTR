const CATEGORIES = ["", "general", "tech", "science", "economy", "politics", "conflict", "environment", "sports"];

function AskSilviaLink({ event }) {
  function handleClick(e) {
    e.stopPropagation();
    const query = encodeURIComponent(
      `SILVIA, brief me on this event: "${event.title}" (${event.category}, ${event.primary_country || "Global"}). ` +
      `Context: ${event.summary || event.snippet || ""}`
    );
    window.open(`${window.location.origin}/?q=${query}`, "_blank", "noopener,noreferrer");
  }
  return (
    <button
      type="button"
      onClick={handleClick}
      style={{
        background: "transparent",
        border: "1px solid var(--accent)",
        color: "var(--accent)",
        fontSize: "0.65rem",
        padding: "0.15rem 0.5rem",
        borderRadius: "3px",
        cursor: "pointer",
        letterSpacing: "0.08em",
      }}
    >
      ASK SILVIA
    </button>
  );
}

export default function EventFeed({
  events,
  selectedEventId,
  onSelect,
  loading,
  error,
  category,
  country,
  countries,
  onRefresh,
}) {
  return (
    <section className="intel-feed panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">World Intelligence / Live Feed</p>
          <h2>Intel Stream</h2>
        </div>
        <button className="panel-button" type="button" onClick={() => onRefresh()}>
          Refresh
        </button>
      </div>

      <div className="filter-row">
        {CATEGORIES.map((option) => (
          <button
            key={option || "all"}
            type="button"
            className={`chip ${category === option ? "chip--active" : ""}`}
            onClick={() => onRefresh({ category: option, country })}
          >
            {option || "all"}
          </button>
        ))}
      </div>

      <div className="mini-form">
        <select value={country} onChange={(e) => onRefresh({ category, country: e.target.value })}>
          <option value="All regions">All regions</option>
          {countries.map((item) => (
            <option key={item} value={item}>
              {item === "United Kingdom" ? "UK" : item}
            </option>
          ))}
        </select>
      </div>

      {loading ? <p className="muted">Refreshing world intelligence...</p> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      <div className="event-feed-list">
        {events.map((evt) => (
          <article
            key={evt.id}
            className={`event-card ${selectedEventId === evt.id ? "event-card--selected" : ""} ${evt.is_global ? "event-card--global" : ""} priority--${evt.board_priority || "low"}`}
            onClick={() => onSelect(evt.id)}
          >
            <div className="event-card__head">
              <strong>{evt.is_global ? "Global" : (evt.primary_country === "United Kingdom" ? "UK" : (evt.primary_country || evt.country || "Unknown"))}</strong>
              <div className="card-tags">
                <span className={`severity severity--${evt.board_priority || evt.severity}`}>{evt.board_priority || evt.severity}</span>
                {evt.badge && <span className="event-badge">{evt.badge}</span>}
              </div>
            </div>

            <div style={{ marginBottom: "0.25rem" }}>
              <span style={{ fontSize: "0.6rem", color: "var(--muted)", letterSpacing: "0.1em" }}>OBSERVATION</span>
              <h3 style={{ margin: "0.1rem 0 0" }}>{evt.title}</h3>
            </div>

            {(evt.summary || evt.snippet) && (
              <div style={{ marginBottom: "0.25rem" }}>
                <span style={{ fontSize: "0.6rem", color: "var(--muted)", letterSpacing: "0.1em" }}>ASSESSMENT</span>
                <p style={{ margin: "0.1rem 0 0", fontSize: "0.8rem" }}>{evt.summary || evt.snippet}</p>
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "0.4rem" }}>
              <p className="muted" style={{ fontSize: "0.68rem" }}>
                {evt.category} · {evt.source_name} · #{evt.final_rank || "—"}
              </p>
              <AskSilviaLink event={evt} />
            </div>

            {evt.secondary_countries?.length ? (
              <p className="muted" style={{ fontSize: "0.68rem" }}>Related: {evt.secondary_countries.join(", ")}</p>
            ) : null}
            {evt.source_url ? (
              <a className="source-link" href={evt.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                Source ↗
              </a>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
