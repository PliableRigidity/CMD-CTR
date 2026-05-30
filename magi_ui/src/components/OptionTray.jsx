export default function OptionTray({ actions, onSelect }) {
  return (
    <section className="option-frame">
      <div className="option-header">
        <h2>Solution Options</h2>
        <span className="option-header-hint">Select an option to view full analysis</span>
      </div>

      <div className="option-row">
        {actions.length ? (
          actions.map((action, i) => (
            <button
              className="option-card"
              key={action.id}
              type="button"
              onClick={() => onSelect(action)}
            >
              <span className="option-card-idx">OPT-{String(i + 1).padStart(2, "0")}</span>
              <span className="option-card-label">{action.title || `Option ${i + 1}`}</span>
            </button>
          ))
        ) : (
          <div className="option-empty">No options generated — awaiting deliberation.</div>
        )}
      </div>
    </section>
  );
}
