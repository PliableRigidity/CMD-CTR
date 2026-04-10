export default function OptionTray({ actions, onSelect }) {
  return (
    <section className="option-frame">
      <div className="option-header">
        <h2>Solution Options</h2>
        <span>Open each item for full content</span>
      </div>

      <div className="option-row">
        {actions.length ? (
          actions.map((action, index) => (
            <button
              className="option-box"
              key={action.id}
              type="button"
              onClick={() => onSelect(action)}
            >
              Option {index + 1}
            </button>
          ))
        ) : (
          <div className="option-empty">No options generated yet.</div>
        )}
      </div>
    </section>
  );
}
