import { useState } from "react";
import { getApiKey, setApiKey } from "../../lib/api";

export default function ApiKeyModal({ onClose, triggered401 = false }) {
  const existing = getApiKey();
  const [value, setValue] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);

  function handleSave() {
    setApiKey(value.trim());
    setSaved(true);
    setTimeout(onClose, 800);
  }

  function handleClear() {
    setApiKey("");
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-panel" role="dialog" aria-modal="true" aria-label="API Authentication">
        <div className="modal-header">
          <span className="modal-title">API Authentication</span>
          <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="modal-body">
          {triggered401 && (
            <p className="modal-alert">
              ⚠ Access denied (401). Set your API key to continue.
            </p>
          )}

          <p className="modal-desc">
            {existing
              ? "An API key is stored. Enter a new key to replace it, or clear it to disable authentication."
              : "No API key configured. If the backend requires authentication (API_KEY env var is set), enter your key below."}
          </p>

          {existing && !value && (
            <div className="modal-current">
              <span className="modal-meta-label">Current key</span>
              <span className="modal-key-mask">{"•".repeat(16)} (set)</span>
            </div>
          )}

          <label className="modal-label">
            New API key
            <div className="modal-input-row">
              <input
                className="modal-input"
                type={showKey ? "text" : "password"}
                placeholder="Enter API key"
                value={value}
                onChange={(e) => { setValue(e.target.value); setSaved(false); }}
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && value.trim() && handleSave()}
              />
              <button
                type="button"
                className="modal-peek"
                onClick={() => setShowKey((v) => !v)}
                tabIndex={-1}
                aria-label={showKey ? "Hide key" : "Show key"}
              >
                {showKey ? "hide" : "show"}
              </button>
            </div>
          </label>
        </div>

        <div className="modal-footer">
          <button
            className="modal-btn modal-btn--primary"
            disabled={!value.trim() || saved}
            onClick={handleSave}
          >
            {saved ? "Saved ✓" : "Save key"}
          </button>
          {existing && (
            <button className="modal-btn modal-btn--danger" onClick={handleClear}>
              Clear key
            </button>
          )}
          <button className="modal-btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
