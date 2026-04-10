import { useState } from "react";

export default function DecisionInputPanel({ onSubmit, busy }) {
  const [problem, setProblem] = useState("");
  const [goal, setGoal] = useState("");
  const [constraints, setConstraints] = useState("");

  function submit(event) {
    event.preventDefault();
    onSubmit({
      problem,
      goal,
      constraints: constraints
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
    });
  }

  return (
    <form className="input-frame" onSubmit={submit}>
      <div className="terminal-line">
        <span className="terminal-label">question:</span>
        <textarea
          className="terminal-textarea"
          value={problem}
          onChange={(event) => setProblem(event.target.value)}
          placeholder="Enter the situation or decision context"
          rows={2}
          required
        />
      </div>

      <div className="terminal-grid">
        <label className="terminal-line">
          <span className="terminal-label">goal:</span>
          <input
            className="terminal-input"
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="Optional goal"
          />
        </label>

        <label className="terminal-line terminal-line-constraints">
          <span className="terminal-label">constraints:</span>
          <textarea
            className="terminal-textarea terminal-textarea-small terminal-textarea-constraints"
            value={constraints}
            onChange={(event) => setConstraints(event.target.value)}
            placeholder="One constraint per line"
            rows={2}
          />
        </label>
      </div>

      <div className="input-footer">
        <button type="submit" disabled={busy || !problem.trim()}>
          {busy ? "PROCESSING" : "EXECUTE"}
        </button>
      </div>
    </form>
  );
}
