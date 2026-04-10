import { useState } from "react";

export default function ActionShortcutsPanel({ actions, audio, onRunAction, onRunAliasAction, onAudioAction }) {
  const [manualTarget, setManualTarget] = useState("");
  const [volumeInput, setVolumeInput] = useState(audio?.volume_percent ?? 50);

  async function submitManual(event) {
    event.preventDefault();
    if (!manualTarget.trim()) {
      return;
    }
    await onRunAliasAction(manualTarget.trim());
    setManualTarget("");
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Action Grid / Control Registry</p>
          <h2>Shortcut Registry</h2>
        </div>
      </div>

      <form className="mini-form" onSubmit={submitManual}>
        <input
          value={manualTarget}
          onChange={(event) => setManualTarget(event.target.value)}
          placeholder="open youtube, github, spotify, terminal..."
        />
        <button type="submit">Run</button>
      </form>

      <div className="action-list">
        {actions.map((action) => (
          <article className="action-card" key={action.id}>
            <div className="action-card__head">
              <strong>{action.label}</strong>
              <span>{action.kind}</span>
            </div>
            <p>{action.description}</p>
            <code>{action.target}</code>
            <button className="panel-button" type="button" onClick={() => onRunAction(action)}>
              Execute
            </button>
          </article>
        ))}
      </div>

      <div className="audio-controls">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">PC Control / Audio Bus</p>
            <h2>Audio</h2>
          </div>
          <span className="muted">
            {audio?.volume_percent != null ? `${audio.volume_percent}%` : "Unavailable"}
          </span>
        </div>

        <div className="button-row">
          <button type="button" className="panel-button" onClick={() => onAudioAction("down")}>Vol -</button>
          <button type="button" className="panel-button" onClick={() => onAudioAction("up")}>Vol +</button>
          <button type="button" className="panel-button" onClick={() => onAudioAction("mute")}>
            {audio?.muted ? "Unmute" : "Mute"}
          </button>
        </div>

        <div className="mini-form mini-form--inline">
          <input
            type="number"
            min="0"
            max="100"
            value={volumeInput}
            onChange={(event) => setVolumeInput(event.target.value)}
          />
          <button type="button" onClick={() => onAudioAction("set", Number(volumeInput))}>Set</button>
        </div>

        <div className="button-row">
          <button type="button" className="panel-button" onClick={() => onAudioAction("play_pause")}>Play/Pause</button>
          <button type="button" className="panel-button" onClick={() => onAudioAction("previous")}>Prev</button>
          <button type="button" className="panel-button" onClick={() => onAudioAction("next")}>Next</button>
        </div>
      </div>
    </section>
  );
}
