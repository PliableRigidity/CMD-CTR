const DEFAULT_AGENTS = [
  {
    name: "SARASWATI",
    role: "Logic · Structure · Feasibility",
    state: "idle",
    summary: "Awaiting decision query. Will evaluate rational feasibility and execution risk.",
  },
  {
    name: "LAKSHMI",
    role: "Safety · Ethics · Stability",
    state: "idle",
    summary: "Awaiting decision query. Will assess harm reduction, sustainability, and fairness.",
  },
  {
    name: "DURGA",
    role: "Intuition · Transformation · Upside",
    state: "idle",
    summary: "Awaiting decision query. Will identify breakthrough potential and hidden opportunity.",
  },
  {
    name: "VIVEKA",
    role: "Chair · Council Synthesis",
    state: "idle",
    summary: "Will synthesize council votes and issue the final recommendation.",
  },
];

const STATE_VERBS = {
  idle: "Standby",
  active: "Analyzing...",
  processing: "Deliberating...",
  complete: "Position Filed",
};

export default function DecisionEnginePanel({ mode, message }) {
  const agents = message?.agents?.length ? message.agents : DEFAULT_AGENTS;
  const isActive = mode === "decision";

  return (
    <section className="panel decision-dock">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Strategic Reasoning / Multi-Agent Council</p>
          <h2>MAGI Subsystem</h2>
        </div>
        <span className={`state-pill state-pill--${isActive ? "busy" : "idle"}`}>
          {isActive ? "Council Active" : "Council Docked"}
        </span>
      </div>

      {isActive && (
        <div className="channel-statusbar" style={{ marginBottom: "0.5rem" }}>
          <span>DELIBERATION BUS / LIVE</span>
          <span>SARASWATI · LAKSHMI · DURGA</span>
          <span>VIVEKA CHAIR</span>
        </div>
      )}

      <div className="agent-grid">
        {agents.map((agent) => (
          <article className="agent-card" key={agent.name}>
            <div className="agent-card__head">
              <strong>{agent.name}</strong>
              <span>{agent.role}</span>
            </div>
            <p className={`agent-state agent-state--${agent.state}`}>
              {STATE_VERBS[agent.state] || agent.state}
            </p>
            <p>{agent.summary}</p>
            {agent.confidence != null ? (
              <div style={{ marginTop: "0.3rem" }}>
                <div style={{
                  height: "3px",
                  background: "var(--border)",
                  borderRadius: "2px",
                  overflow: "hidden",
                }}>
                  <div style={{
                    height: "100%",
                    width: `${agent.confidence}%`,
                    background: "var(--accent)",
                    transition: "width 0.4s ease",
                  }} />
                </div>
                <p className="agent-confidence" style={{ marginTop: "0.2rem" }}>
                  Confidence {agent.confidence}%
                </p>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
