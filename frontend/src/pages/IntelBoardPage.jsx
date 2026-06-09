import { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import GlobeComponent from "../components/globe/GlobeComponent";
import { getInitialState, startSimulation } from "../data/mockEngine";
import { maritimeRoutes } from "../data/maritimeRoutes";
import { publicCameras } from "../data/cameras";
import { fetchWorldEvents } from "../lib/api";

// ── Market Ticker Bar ──────────────────────────────────────────────────────
function MarketTicker({ markets }) {
  const entries = Object.values(markets);
  return (
    <div className="flex gap-6 overflow-x-auto py-1 px-2 text-xs font-mono">
      {entries.map(m => (
        <div key={m.symbol} className="flex items-center gap-2 whitespace-nowrap">
          <span className="text-cyan-400 font-bold">{m.symbol}</span>
          <span className="text-slate-200">${m.price.toFixed(2)}</span>
          <span className={m.change >= 0 ? "text-emerald-400" : "text-red-400"}>
            {m.change >= 0 ? "▲" : "▼"} {Math.abs(m.changePercent).toFixed(2)}%
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Live Stats Bar ─────────────────────────────────────────────────────────
function StatsBadge({ icon, label, value, color = "cyan" }) {
  const colors = {
    cyan: "border-cyan-500/40 text-cyan-400",
    red: "border-red-500/40 text-red-400",
    blue: "border-blue-500/40 text-blue-400",
    amber: "border-amber-500/40 text-amber-400",
    teal: "border-teal-500/40 text-teal-400",
  };
  return (
    <div className={`flex items-center gap-1.5 border rounded px-2 py-0.5 text-xs font-mono ${colors[color]}`}>
      <span>{icon}</span>
      <span className="text-slate-400">{label}</span>
      <span className="font-bold">{value}</span>
    </div>
  );
}

// ── Event Detail Panel ─────────────────────────────────────────────────────
function EventPanel({ event, onClose }) {
  if (!event) return null;
  const { type, data } = event;

  const title =
    type === "threat" ? `⚠️ Threat — ${data.region}` :
    type === "earthquake" ? `🌍 Magnitude ${data.mag?.toFixed(1)} Earthquake` :
    type === "flight" ? `✈️ Flight ${data.callsign}` :
    type === "ship" ? `🚢 ${data.type}` :
    type === "weather" ? `${data.name} Weather` :
    type === "volcano" ? `🌋 ${data.name}` :
    type === "radiation" ? `☢️ ${data.name}` :
    type === "route" ? `⚓ ${data.name}` :
    type === "worldEvent" ? `📡 ${data.title || data.category}` :
    "Intel Detail";

  return (
    <div className="absolute bottom-4 left-4 z-20 w-80 bg-slate-900/95 border border-cyan-500/30 rounded-lg p-4 backdrop-blur shadow-2xl">
      <div className="flex justify-between items-start mb-2">
        <h3 className="text-sm font-bold text-slate-100 leading-tight">{title}</h3>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200 text-lg leading-none ml-2">×</button>
      </div>
      <div className="space-y-1 text-xs text-slate-400">
        {type === "threat" && <>
          <p><span className="text-slate-500">Severity:</span> <span className="text-orange-400 font-bold">{"★".repeat(data.weight)}</span></p>
          <p><span className="text-slate-500">Headline:</span> {data.headline}</p>
          <p><span className="text-slate-500">Region:</span> {data.region}</p>
        </>}
        {type === "earthquake" && <>
          <p><span className="text-slate-500">Title:</span> {data.title}</p>
          <p><span className="text-slate-500">Magnitude:</span> <span className="text-red-400 font-bold">{data.mag?.toFixed(1)}</span></p>
          <p><span className="text-slate-500">Time:</span> {new Date(data.time).toLocaleString()}</p>
        </>}
        {type === "flight" && <>
          <p><span className="text-slate-500">Callsign:</span> {data.callsign}</p>
          <p><span className="text-slate-500">Country:</span> {data.country}</p>
          <p><span className="text-slate-500">Altitude:</span> {data.alt?.toFixed(0)} ft</p>
          <p><span className="text-slate-500">Velocity:</span> {data.velocity?.toFixed(0)} kts</p>
        </>}
        {type === "ship" && <>
          <p><span className="text-slate-500">Type:</span> {data.type}</p>
          <p><span className="text-slate-500">MMSI:</span> {data.mmsi}</p>
          <p><span className="text-slate-500">Speed:</span> {data.speed?.toFixed(1)} kts</p>
        </>}
        {type === "weather" && <>
          <p><span className="text-slate-500">Location:</span> {data.name}</p>
          <p><span className="text-slate-500">Condition:</span> {data.condition}</p>
          <p><span className="text-slate-500">Temperature:</span> {data.temp?.toFixed(1)}°C</p>
          <p><span className="text-slate-500">Wind:</span> {data.wind?.toFixed(1)} m/s</p>
        </>}
        {type === "volcano" && <>
          <p><span className="text-slate-500">Status:</span> <span className="text-orange-400">{data.status}</span></p>
          <p><span className="text-slate-500">Region:</span> {data.region}</p>
          <p><span className="text-slate-500">VEI:</span> {data.vei}</p>
        </>}
        {type === "radiation" && <>
          <p><span className="text-slate-500">CPM:</span> <span className={data.alert ? "text-fuchsia-400 font-bold" : ""}>{data.cpm}</span></p>
          <p><span className="text-slate-500">Status:</span> <span className={data.alert ? "text-red-400" : "text-emerald-400"}>{data.alert ? "⚠️ ELEVATED" : "✓ Normal"}</span></p>
        </>}
        {type === "route" && <>
          <p><span className="text-slate-500">Traffic:</span> {data.traffic}</p>
          <p><span className="text-slate-500">Tonnage:</span> {data.tonnage}</p>
          <p><span className="text-slate-500">Importance:</span> <span className="text-cyan-400">{data.importance}</span></p>
          <p className="mt-1 text-slate-500 leading-relaxed">{data.description?.slice(0, 180)}…</p>
        </>}
        {type === "worldEvent" && <>
          <p><span className="text-slate-500">Category:</span> {data.category}</p>
          {data.primary_country && <p><span className="text-slate-500">Country:</span> {data.primary_country}</p>}
          {data.snippet && <p className="mt-1 text-slate-500 leading-relaxed">{data.snippet?.slice(0, 180)}</p>}
          {data.url && <a href={data.url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">Open source ↗</a>}
        </>}
      </div>
    </div>
  );
}

// ── Threat Feed Sidebar ────────────────────────────────────────────────────
function ThreatFeed({ threats, worldEvents }) {
  const combined = [
    ...threats.slice(0, 5).map(t => ({ key: t.id, icon: "⚠️", text: t.headline, sub: t.region, color: "text-orange-400" })),
    ...worldEvents.slice(0, 5).map(e => ({ key: e.id, icon: "📡", text: e.title, sub: e.primary_country || e.category, color: "text-teal-400" })),
  ].slice(0, 8);

  return (
    <div className="flex flex-col gap-1 overflow-y-auto max-h-64">
      {combined.map(item => (
        <div key={item.key} className="flex gap-2 p-2 rounded bg-slate-800/60 border border-slate-700/40 text-xs">
          <span>{item.icon}</span>
          <div>
            <p className={`font-semibold ${item.color} leading-tight`}>{item.text}</p>
            {item.sub && <p className="text-slate-500 text-[10px] mt-0.5">{item.sub}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function IntelBoardPage() {
  const [simData, setSimData] = useState(() => getInitialState());
  const [worldEvents, setWorldEvents] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [clock, setClock] = useState(new Date());
  const stopSimRef = useRef(null);

  // Start palantir simulation
  useEffect(() => {
    const stop = startSimulation(setSimData);
    stopSimRef.current = stop;
    return stop;
  }, []);

  // Load CMD-CTR real world events and poll every 60s
  useEffect(() => {
    async function loadEvents() {
      try {
        const data = await fetchWorldEvents({ live: true });
        setWorldEvents(Array.isArray(data) ? data : []);
      } catch { /* silently degrade */ }
    }
    loadEvents();
    const interval = setInterval(loadEvents, 60000);
    return () => clearInterval(interval);
  }, []);

  // Clock
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const handleEventSelect = (type, data) => setSelectedEvent({ type, data });
  const handleCameraSelect = (id) => {
    const cam = publicCameras.find(c => c.id === id);
    if (cam) setSelectedEvent({ type: "camera", data: cam });
  };

  const markets = simData.markets || {};

  return (
    <div className="relative w-screen h-screen bg-slate-950 overflow-hidden font-mono">
      {/* Background glow */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(14,165,233,0.05)_0%,transparent_70%)] pointer-events-none" />

      {/* ── Top Bar ── */}
      <header className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-4 py-2 bg-slate-950/90 backdrop-blur border-b border-cyan-500/20">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-xs text-cyan-500 hover:text-cyan-300 border border-cyan-500/30 rounded px-2 py-1 hover:bg-cyan-500/10 transition-colors">
            ← SILVIA
          </Link>
          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-widest">Global Intelligence Board</p>
            <h1 className="text-sm font-bold text-slate-100 leading-none">PALANTIR INTEL — LIVE FEED</h1>
          </div>
        </div>

        <div className="hidden md:flex gap-2 flex-wrap">
          <StatsBadge icon="✈️" label="Flights" value={simData.flights?.length} color="blue" />
          <StatsBadge icon="🚢" label="Ships" value={simData.ships?.length} color="cyan" />
          <StatsBadge icon="⚠️" label="Threats" value={simData.threats?.length} color="red" />
          <StatsBadge icon="🌍" label="Seismic" value={simData.earthquakes?.length} color="amber" />
          <StatsBadge icon="📡" label="Live Events" value={worldEvents.length} color="teal" />
        </div>

        <div className="text-right">
          <p className="text-xs text-cyan-400 font-bold tabular-nums">{clock.toUTCString().slice(17, 25)} UTC</p>
          <p className="text-[10px] text-slate-500">{clock.toDateString()}</p>
        </div>
      </header>

      {/* ── Market Ticker ── */}
      <div className="absolute top-[52px] left-0 right-0 z-20 bg-slate-900/80 backdrop-blur border-b border-slate-700/40 px-2">
        <MarketTicker markets={markets} />
      </div>

      {/* ── Globe (full screen) ── */}
      <div className="absolute inset-0 pt-[76px]">
        <GlobeComponent
          threats={simData.threats}
          cameras={publicCameras}
          earthquakes={simData.earthquakes}
          flights={simData.flights}
          weather={simData.weather}
          lightning={simData.lightning}
          ships={simData.ships}
          volcanoes={simData.volcanoes}
          radiation={simData.radiation}
          maritimeRoutes={maritimeRoutes}
          worldEvents={worldEvents}
          onEventSelect={handleEventSelect}
          onCameraSelect={handleCameraSelect}
        />
      </div>

      {/* ── Event Detail Panel ── */}
      {selectedEvent && (
        <EventPanel event={selectedEvent} onClose={() => setSelectedEvent(null)} />
      )}

      {/* ── Sidebar Toggle ── */}
      <button
        onClick={() => setSidebarOpen(v => !v)}
        className="absolute top-20 right-4 z-30 bg-slate-900/80 border border-cyan-500/30 text-cyan-400 text-xs px-2 py-1 rounded hover:bg-slate-800/80 transition-colors"
      >
        {sidebarOpen ? "Hide ›" : "‹ Intel"}
      </button>

      {/* ── Right Sidebar ── */}
      {sidebarOpen && (
        <aside className="absolute top-[76px] right-0 bottom-0 z-20 w-72 bg-slate-950/90 backdrop-blur border-l border-cyan-500/20 flex flex-col overflow-hidden">
          <div className="p-3 border-b border-slate-700/40">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest">Live Intelligence Feed</p>
          </div>

          {/* Layer legend */}
          <div className="p-3 border-b border-slate-700/40 grid grid-cols-2 gap-1 text-[10px]">
            {[
              { dot: "bg-sky-400", label: "Flights" },
              { dot: "bg-blue-300", label: "Ships" },
              { dot: "bg-red-500", label: "Seismic" },
              { dot: "bg-orange-400", label: "Threats" },
              { dot: "bg-teal-400", label: "Live Events" },
              { dot: "bg-cyan-400", label: "Cameras" },
              { dot: "bg-orange-500", label: "Volcanoes" },
              { dot: "bg-fuchsia-500", label: "Radiation" },
            ].map(({ dot, label }) => (
              <div key={label} className="flex items-center gap-1.5 text-slate-400">
                <span className={`w-2 h-2 rounded-full ${dot} inline-block`} />
                {label}
              </div>
            ))}
          </div>

          {/* Threat + event feed */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Active Threats & Events</p>
              <ThreatFeed threats={simData.threats} worldEvents={worldEvents} />
            </div>

            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Recent Seismic Activity</p>
              <div className="space-y-1">
                {simData.earthquakes?.slice(0, 5).map(eq => (
                  <div key={eq.id} className="flex justify-between items-center text-[10px] p-1.5 bg-slate-800/50 rounded border border-slate-700/30">
                    <span className="text-slate-400 truncate">{eq.title}</span>
                    <span className="text-red-400 font-bold ml-2">M{eq.mag?.toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Radiation Monitors</p>
              <div className="space-y-1">
                {simData.radiation?.map(r => (
                  <div key={r.id} className={`flex justify-between items-center text-[10px] p-1.5 rounded border ${r.alert ? "bg-fuchsia-950/30 border-fuchsia-500/30" : "bg-slate-800/30 border-slate-700/30"}`}>
                    <span className="text-slate-400 truncate text-[9px]">{r.name}</span>
                    <span className={r.alert ? "text-fuchsia-400 font-bold" : "text-slate-500"}>{r.cpm} cpm</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Status footer */}
          <div className="p-3 border-t border-slate-700/40 flex justify-between text-[9px] text-slate-600">
            <span>⬤ LIVE SIMULATION</span>
            <span>⬤ {worldEvents.length} RSS EVENTS</span>
          </div>
        </aside>
      )}

      {/* ── Bottom Legend ── */}
      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-20 text-[9px] text-slate-600 text-center pointer-events-none">
        Drag to rotate · Scroll to zoom · Click any marker for details
      </div>
    </div>
  );
}
