const DEFAULT_AGENTS = [
  { name: "SARASWATI", role: "Logic", state: "idle", summary: "No decision request has been submitted yet." },
  { name: "LAKSHMI", role: "Emotion", state: "idle", summary: "No decision request has been submitted yet." },
  { name: "DURGA", role: "Intuition", state: "idle", summary: "No decision request has been submitted yet." },
  { name: "VIVEKA", role: "Chair", state: "idle", summary: "The MAGI chair will summarize after a decision run." },
];

export default function DecisionEnginePanel({ mode, message }) {
  const agents = message?.agents?.length ? message.agents : DEFAULT_AGENTS;

  return (
    <section className="panel decision-dock">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Decision Engine</p>
          <h2>MAGI Subsystem</h2>
        </div>
        <span className={`state-pill state-pill--${mode === "decision" ? "busy" : "idle"}`}>
          {mode === "decision" ? "Decision Mode Active" : "Decision Mode Docked"}
        </span>
      </div>

      <div className="agent-grid">
        {agents.map((agent) => (
          <article className="agent-card" key={agent.name}>
            <div className="agent-card__head">
              <strong>{agent.name}</strong>
              <span>{agent.role}</span>
            </div>
            <p className={`agent-state agent-state--${agent.state}`}>{agent.state}</p>
            <p>{agent.summary}</p>
            {agent.confidence ? <p className="agent-confidence">Confidence {agent.confidence}%</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
