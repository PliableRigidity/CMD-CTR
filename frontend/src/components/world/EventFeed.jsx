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
  const categories = ["", "general", "tech", "science", "economy", "politics", "conflict", "environment", "sports"];

  return (
    <section className="intel-feed panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">World Intel</p>
          <h2>Live Event Feed</h2>
        </div>
        <button className="panel-button" type="button" onClick={() => onRefresh()}>
          Refresh
        </button>
      </div>

      <div className="filter-row">
        {categories.map((option) => (
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
        <select value={country} onChange={(event) => onRefresh({ category, country: event.target.value })}>
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
        {events.map((eventItem) => (
          <article
            key={eventItem.id}
            className={`event-card ${selectedEventId === eventItem.id ? "event-card--selected" : ""} ${eventItem.is_global ? "event-card--global" : ""} priority--${eventItem.board_priority || "low"}`}
            onClick={() => onSelect(eventItem.id)}
          >
            <div className="event-card__head">
              <strong>{eventItem.is_global ? "Global" : (eventItem.primary_country === "United Kingdom" ? "UK" : (eventItem.primary_country || eventItem.country))}</strong>
              <div className="card-tags">
                <span className={`severity severity--${eventItem.board_priority || eventItem.severity}`}>{eventItem.board_priority || eventItem.severity}</span>
                {eventItem.badge && <span className="event-badge">{eventItem.badge}</span>}
              </div>
            </div>
            <h3>{eventItem.title}</h3>
            <p>{eventItem.summary}</p>
            <p className="muted">
              {eventItem.category} | {eventItem.source_name} | Rank: {eventItem.final_rank || 'N/A'}
            </p>
            {eventItem.secondary_countries?.length ? (
              <p className="muted">Related: {eventItem.secondary_countries.join(", ")}</p>
            ) : null}
            {eventItem.is_global ? <p className="muted">No geographic pin for this story.</p> : null}
            {eventItem.source_url ? (
              <a className="source-link" href={eventItem.source_url} target="_blank" rel="noreferrer">
                Open source
              </a>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
