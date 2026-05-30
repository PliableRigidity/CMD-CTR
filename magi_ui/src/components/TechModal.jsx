export default function TechModal({ open, title, children, onClose }) {
  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="modal-shell"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="modal-close-btn" type="button" onClick={onClose}>
            ESC
          </button>
        </div>

        <div className="modal-body">{children}</div>

        <div className="modal-footer">
          <button className="modal-action-btn" type="button" onClick={onClose}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
