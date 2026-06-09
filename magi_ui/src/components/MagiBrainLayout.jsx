import { useEffect, useLayoutEffect, useRef, useState } from "react";

const BRAIN_META = {
  SARASWATI: { role: "Logic · Analysis", serial: "SARAS-1" },
  LAKSHMI:   { role: "Values · Intuition", serial: "LAK-2" },
  DURGA:     { role: "Action · Risk", serial: "DURG-3" },
};

const PANELS = [
  { brain: "SARASWATI", position: "top" },
  { brain: "LAKSHMI",   position: "left" },
  { brain: "DURGA",     position: "right" },
];

function getStateLabel(state) {
  switch (state) {
    case "processing": return "DELIBERATING";
    case "yes":        return "APPROVED";
    case "no":         return "DISSENT";
    case "abstain":    return "ABSTAIN";
    default:           return "STANDBY";
  }
}

function StatusBadge({ phase, majorityDecision }) {
  const [pulsing, setPulsing] = useState(false);

  useEffect(() => {
    if (phase !== "processing") { setPulsing(false); return; }
    let t1, t2;
    let cancelled = false;
    const rand = (a, b) => Math.floor(Math.random() * (b - a + 1)) + a;
    const cycle = () => {
      t1 = window.setTimeout(() => {
        if (cancelled) return;
        setPulsing(true);
        t2 = window.setTimeout(() => {
          if (cancelled) return;
          setPulsing(false);
          cycle();
        }, rand(60, 130));
      }, rand(90, 320));
    };
    cycle();
    return () => { cancelled = true; clearTimeout(t1); clearTimeout(t2); };
  }, [phase]);

  let statusClass = "status-idle";
  let kanji = "待機";
  let latin = "STANDBY";

  if (phase === "processing") {
    statusClass = "status-processing";
    kanji = pulsing ? "情報" : "情報";
    latin = "PROCESSING";
  } else if (majorityDecision) {
    const d = String(majorityDecision).toUpperCase();
    if (d === "NO" || d === "REJECTED") {
      statusClass = "status-rejected";
      kanji = "拒絶";
      latin = "REJECTED";
    } else if (d === "ABSTAIN" || d === "UNDECIDED") {
      statusClass = "status-undecided";
      kanji = "棄権";
      latin = "UNDECIDED";
    } else {
      statusClass = "status-approved";
      kanji = "容認";
      latin = "APPROVED";
    }
  }

  return (
    <div className={`magi-status-badge ${statusClass}`}>
      <div className="status-dot" />
      <div className="status-latin">{latin}</div>
      <div className="status-kanji">{kanji}</div>
    </div>
  );
}

export default function MagiBrainLayout({ brainStates, votes, majorityDecision, phase }) {
  const frameRef = useRef(null);
  const topRef   = useRef(null);
  const leftRef  = useRef(null);
  const rightRef = useRef(null);
  const [trianglePoints, setTrianglePoints] = useState([]);

  useLayoutEffect(() => {
    const frame = frameRef.current;
    const top   = topRef.current;
    const left  = leftRef.current;
    const right = rightRef.current;
    if (!frame || !top || !left || !right) return;

    function recalc() {
      const fr = frame.getBoundingClientRect();
      const tr = top.getBoundingClientRect();
      const lr = left.getBoundingClientRect();
      const rr = right.getBoundingClientRect();

      const cx = fr.width / 2;
      const topY  = tr.bottom - fr.top;
      const leftY = lr.top - fr.top + lr.height / 2;
      const rightY = rr.top - fr.top + rr.height / 2;
      const gapW = Math.max((rr.left - fr.left) - (lr.right - fr.left), 0);
      const tw = gapW * 1.5;
      const th = tw * 1.2;
      const midY = (leftY + rightY) / 2;

      setTrianglePoints([
        { x: cx,          y: topY - 260 },
        { x: cx - tw / 2, y: Math.min(midY, topY - 260 + th) + 30 },
        { x: cx + tw / 2, y: Math.min(midY, topY - 260 + th) + 30 },
      ]);
    }

    const obs = new ResizeObserver(recalc);
    [frame, top, left, right].forEach((el) => obs.observe(el));
    window.addEventListener("resize", recalc);
    recalc();
    return () => { obs.disconnect(); window.removeEventListener("resize", recalc); };
  }, []);

  return (
    <section className="magi-frame" ref={frameRef}>
      {/* Header bar */}
      <div className="magi-header-bar">
        <div className="magi-wordmark">MAGI SYSTEM</div>
        <div className="magi-build-tag">BUILD 4.0 · SILVIA</div>
      </div>

      {/* Left metadata */}
      <aside className="system-dossier">
        <p className="dossier-id">CODE:473</p>
        <p><span className="dossier-key">FILE</span><span className="dossier-val">MAGI.SYS</span></p>
        <p><span className="dossier-key">EXT</span><span className="dossier-val">3023</span></p>
        <p><span className="dossier-key">MODE</span><span className="dossier-val">{phase === "processing" ? "RUN" : "OFF"}</span></p>
        <p><span className="dossier-key">PRI</span><span className="dossier-val">AAA</span></p>
      </aside>

      {/* Right status badge */}
      <StatusBadge phase={phase} majorityDecision={majorityDecision} />

      {/* Brain panels */}
      {PANELS.map((panel) => (
        <BrainPanel
          key={panel.brain}
          panelRef={
            panel.position === "top"   ? topRef  :
            panel.position === "left"  ? leftRef :
            rightRef
          }
          name={panel.brain}
          meta={BRAIN_META[panel.brain]}
          position={panel.position}
          state={brainStates[panel.brain]}
          vote={votes?.[panel.brain]?.selected_action}
        />
      ))}

      {/* Triangle connector */}
      <div className="magi-connector-overlay" aria-hidden="true">
        <svg className="magi-connector-svg">
          {trianglePoints.length === 3 && (
            <polygon
              className="magi-triangle"
              points={trianglePoints.map((p) => `${p.x},${p.y}`).join(" ")}
            />
          )}
        </svg>
      </div>

      {/* Center hub */}
      <div className="magi-hub">
        <span className="magi-hub-label">MAGI</span>
        <span className="magi-hub-sub">DELIBERATION ENGINE</span>
      </div>
    </section>
  );
}

function BrainPanel({ name, meta, panelRef, position, state, vote }) {
  const stateLabel = getStateLabel(state);

  return (
    <article
      className={`brain-panel brain-${position} state-${state}`}
      ref={panelRef}
    >
      <div className="brain-panel-inner">
        <div className="brain-header">
          <h2 className="brain-name">{name}</h2>
          <div className="brain-role">{meta.role}</div>
          <div className="brain-serial">{meta.serial}</div>
        </div>

        <div className="brain-footer">
          <div className="brain-state-label">
            <span className="brain-state-dot" />
            {stateLabel}
          </div>
          {vote && state !== "idle" && state !== "processing" && (
            <div className="brain-vote-chip">{vote}</div>
          )}
        </div>
      </div>
    </article>
  );
}
