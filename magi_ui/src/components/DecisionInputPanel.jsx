import { useState } from "react";

export default function DecisionInputPanel({ onSubmit, busy }) {
  const [problem, setProblem]         = useState("");
  const [goal, setGoal]               = useState("");
  const [constraints, setConstraints] = useState("");

  function submit(e) {
    e.preventDefault();
    onSubmit({
      problem,
      goal,
      constraints: constraints
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    });
  }

  return (
    <form className="input-frame" onSubmit={submit}>
      <p className="input-section-label">Decision Input</p>

      <div className="input-row">
        <div className="field-group">
          <label className="field-label" htmlFor="field-problem">Situation / Question</label>
          <textarea
            id="field-problem"
            className="field-textarea"
            value={problem}
            onChange={(e) => setProblem(e.target.value)}
            placeholder="Describe the situation or decision you need evaluated"
            rows={2}
            required
          />
        </div>
      </div>

      <div className="input-meta-row">
        <div className="field-group">
          <label className="field-label" htmlFor="field-goal">Goal</label>
          <input
            id="field-goal"
            className="field-input"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Optional — what outcome are you optimising for?"
          />
        </div>

        <div className="field-group">
          <label className="field-label" htmlFor="field-constraints">Constraints</label>
          <textarea
            id="field-constraints"
            className="field-textarea field-textarea-sm"
            value={constraints}
            onChange={(e) => setConstraints(e.target.value)}
            placeholder="One per line — time limits, resources, hard rules"
            rows={2}
          />
        </div>
      </div>

      <div className="input-footer">
        <button
          className={`btn-execute${busy ? " btn-execute-busy" : ""}`}
          type="submit"
          disabled={busy || !problem.trim()}
        >
          {busy ? "PROCESSING" : "EXECUTE"}
        </button>
      </div>
    </form>
  );
}
