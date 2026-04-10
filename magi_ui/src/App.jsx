import { useMemo, useState } from "react";
import DecisionInputPanel from "./components/DecisionInputPanel";
import MagiBrainLayout from "./components/MagiBrainLayout";
import OptionTray from "./components/OptionTray";
import TechModal from "./components/TechModal";

const API_URL = "http://localhost:8000/api/decide";
const SPECIAL_STATES = new Set(["ABSTAIN", "UNDECIDED"]);

function getPanelStatus({ phase, brainName, result }) {
  if (phase === "processing") {
    return "processing";
  }

  if (phase !== "resolved" || !result?.final_votes?.[brainName]) {
    return "idle";
  }

  const vote = result.final_votes[brainName].selected_action;
  const majority = result.majority_decision;

  if (SPECIAL_STATES.has(vote)) {
    return "abstain";
  }

  if (!SPECIAL_STATES.has(majority)) {
    return vote === majority ? "yes" : "no";
  }

  return "abstain";
}

export default function App() {
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [verdictOpen, setVerdictOpen] = useState(false);
  const [activeOption, setActiveOption] = useState(null);

  const brainStates = useMemo(
    () => ({
      SARASWATI: getPanelStatus({ phase, brainName: "SARASWATI", result }),
      DURGA: getPanelStatus({ phase, brainName: "DURGA", result }),
      LAKSHMI: getPanelStatus({ phase, brainName: "LAKSHMI", result }),
    }),
    [phase, result],
  );

  async function handleSubmit(payload) {
    setError("");
    setResult(null);
    setVerdictOpen(false);
    setActiveOption(null);
    setPhase("processing");

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Decision request failed.");
      }

      const data = await response.json();
      setResult(data);
      setPhase("resolved");
      setVerdictOpen(true);
    } catch (requestError) {
      setError(requestError.message || "Unknown error");
      setPhase("idle");
    }
  }

  return (
    <div className="command-ui">
      <div className="scanlines" />
      <main className="magi-shell">
        {error ? <div className="error-bar">{error}</div> : null}

        <MagiBrainLayout
          brainStates={brainStates}
          votes={result?.final_votes}
          majorityDecision={result?.majority_decision}
          phase={phase}
        />

        <DecisionInputPanel onSubmit={handleSubmit} busy={phase === "processing"} />

        <OptionTray actions={result?.actions ?? []} onSelect={setActiveOption} />

        <section className="signal-grid">
          <article className="telemetry-card">
            <h2>Situation Model</h2>
            <p className="telemetry-line">
              <span>SUMMARY</span>
              <strong>{result?.situation_model?.problem_summary ?? "Awaiting input"}</strong>
            </p>
            <p className="telemetry-line">
              <span>GOAL</span>
              <strong>{result?.situation_model?.goal || "Not provided"}</strong>
            </p>
          </article>

          <article className="telemetry-card">
            <h2>Vote Counts</h2>
            {result?.vote_counts ? (
              Object.entries(result.vote_counts).map(([key, value]) => (
                <p className="telemetry-line" key={key}>
                  <span>{key}</span>
                  <strong>{value}</strong>
                </p>
              ))
            ) : (
              <p className="telemetry-empty">No deliberation yet.</p>
            )}
          </article>
        </section>
      </main>

      <TechModal
        open={verdictOpen}
        title="Final Verdict"
        onClose={() => setVerdictOpen(false)}
      >
        <div className="verdict-block">
          <p className="verdict-label">Majority Decision</p>
          <h2>{result?.majority_decision ?? "N/A"}</h2>
          <p>{result?.chair_summary?.summary ?? "No summary available."}</p>
          <p className="verdict-meta">
            Dominant reasoning: {result?.chair_summary?.dominant_reasoning ?? "N/A"}
          </p>
          <p className="verdict-meta">
            Recommended action: {result?.chair_summary?.recommended_action ?? "N/A"}
          </p>
        </div>
      </TechModal>

      <TechModal
        open={Boolean(activeOption)}
        title={activeOption ? activeOption.id : "Option"}
        onClose={() => setActiveOption(null)}
      >
        {activeOption ? (
          <div className="option-modal-copy">
            <h2>{activeOption.title}</h2>
            <p>{activeOption.description}</p>
          </div>
        ) : null}
      </TechModal>
    </div>
  );
}
