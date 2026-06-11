import { useEffect, useState, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import GlobeComponent from "../components/globe/GlobeComponent";
import { getInitialState, startSimulation } from "../data/mockEngine";
import { maritimeRoutes } from "../data/maritimeRoutes";
import { publicCameras } from "../data/cameras";
import { fetchWorldEvents, fetchStockQuote, fetchEarthquakes, fetchWeather, fetchMarkets } from "../lib/api";

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
          {(data.summary || data.snippet) && <p className="mt-1 text-slate-500 leading-relaxed">{(data.summary || data.snippet)?.slice(0, 180)}</p>}
          {data.assessment && <p><span className="text-slate-500">Assessment:</span> {data.assessment}</p>}
          {data.prediction && <p><span className="text-slate-500">Prediction:</span> {data.prediction}</p>}
          {data.recommendation && <p><span className="text-slate-500">Recommendation:</span> <span className="text-amber-400">{data.recommendation}</span></p>}
          {(data.source_url || data.url) && <a href={data.source_url || data.url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">Open source ↗</a>}
        </>}
      </div>
    </div>
  );
}

// ── Priority colour map ────────────────────────────────────────────────────
const PRIORITY_STYLE = {
  critical: { border: "border-red-500/50",    label: "text-red-400",    bg: "bg-red-950/20"    },
  high:     { border: "border-orange-500/40", label: "text-orange-400", bg: "bg-orange-950/20" },
  medium:   { border: "border-amber-500/30",  label: "text-amber-400",  bg: "bg-amber-950/10"  },
  low:      { border: "border-slate-700/40",  label: "text-slate-400",  bg: ""                 },
};

// ── World Intel Feed with O/A/P cards ─────────────────────────────────────
function WorldIntelFeed({ events, onSelectGlobe }) {
  const [expandedId, setExpandedId] = useState(null);
  const shown = events.slice(0, 15);
  const withAssessment = shown.filter(e => e.assessment).length;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between mb-1 text-[9px] text-slate-500">
        <span>{shown.length} EVENTS</span>
        <span>{withAssessment}/{shown.length} ASSESSED</span>
      </div>

      {shown.map(ev => {
        const isExpanded = expandedId === ev.id;
        const p = PRIORITY_STYLE[ev.board_priority] || PRIORITY_STYLE.low;
        const country = ev.primary_country || ev.country || "Global";

        return (
          <div
            key={ev.id}
            className={`rounded border ${p.border} ${p.bg} cursor-pointer transition-all duration-150 hover:brightness-110`}
            onClick={() => {
              setExpandedId(isExpanded ? null : ev.id);
              onSelectGlobe?.(ev);
            }}
          >
            {/* ── Card header ── */}
            <div className="p-2">
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className={`text-[8px] font-bold uppercase tracking-widest ${p.label}`}>
                  {(ev.board_priority || "LOW").toUpperCase()}
                  {ev.badge ? ` · ${ev.badge}` : ""}
                </span>
                <span className="text-[9px] text-slate-500 tabular-nums">
                  {country} · {ev.category || "general"}
                </span>
              </div>
              <p className="text-[10px] text-slate-100 leading-snug font-medium line-clamp-2">{ev.title}</p>
              {!isExpanded && ev.assessment && (
                <p className="text-[9px] text-cyan-400/70 leading-snug mt-1 line-clamp-1 italic">{ev.assessment}</p>
              )}
            </div>

            {/* ── Expanded O/A/P body ── */}
            {isExpanded && (
              <div className="px-2 pb-2 pt-1 border-t border-slate-700/30 space-y-2">
                <div>
                  <p className="text-[8px] font-bold text-slate-500 uppercase tracking-wider mb-0.5">Observation</p>
                  <p className="text-[10px] text-slate-300 leading-snug">{ev.title}</p>
                </div>
                <div>
                  <p className="text-[8px] font-bold text-cyan-500/80 uppercase tracking-wider mb-0.5">Assessment · SILVIA</p>
                  {ev.assessment
                    ? <p className="text-[10px] text-cyan-300/80 leading-snug">{ev.assessment}</p>
                    : <p className="text-[10px] text-slate-600 italic">Analyzing — check back shortly</p>
                  }
                </div>
                <div>
                  <p className="text-[8px] font-bold text-cyan-500/80 uppercase tracking-wider mb-0.5">Prediction · SILVIA</p>
                  {ev.prediction
                    ? <p className="text-[10px] text-cyan-300/80 leading-snug">{ev.prediction}</p>
                    : <p className="text-[10px] text-slate-600 italic">Pending</p>
                  }
                </div>
                {ev.recommendation && (
                  <div>
                    <p className="text-[8px] font-bold text-amber-500/80 uppercase tracking-wider mb-0.5">Recommendation · SILVIA</p>
                    <p className="text-[10px] text-amber-300/80 leading-snug">{ev.recommendation}</p>
                  </div>
                )}
                <div className="flex items-center justify-between pt-0.5">
                  <span className="text-[9px] text-slate-600">{ev.source_name || ""}</span>
                  {ev.source_url && (
                    <a href={ev.source_url} target="_blank" rel="noreferrer"
                      className="text-[9px] text-cyan-500 hover:underline"
                      onClick={e => e.stopPropagation()}>
                      Source ↗
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}

      {shown.length === 0 && (
        <p className="text-[10px] text-slate-600 text-center py-4">No world events loaded</p>
      )}
    </div>
  );
}

// ── Simulation threat feed ─────────────────────────────────────────────────
function SimFeed({ threats, earthquakes, radiation }) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Active Threats</p>
        <div className="flex flex-col gap-1">
          {threats?.slice(0, 5).map(t => (
            <div key={t.id} className="flex gap-2 p-2 rounded bg-slate-800/60 border border-orange-500/20 text-xs">
              <span>⚠️</span>
              <div>
                <p className="font-semibold text-orange-400 leading-tight">{t.headline}</p>
                <p className="text-slate-500 text-[10px] mt-0.5">{t.region}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Seismic Activity</p>
        <div className="space-y-1">
          {earthquakes?.slice(0, 5).map(eq => (
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
          {radiation?.map(r => (
            <div key={r.id} className={`flex justify-between items-center text-[10px] p-1.5 rounded border ${r.alert ? "bg-fuchsia-950/30 border-fuchsia-500/30" : "bg-slate-800/30 border-slate-700/30"}`}>
              <span className="text-slate-400 truncate text-[9px]">{r.name}</span>
              <span className={r.alert ? "text-fuchsia-400 font-bold" : "text-slate-500"}>{r.cpm} cpm</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Mini SVG Sparkline ────────────────────────────────────────────────────
function Sparkline({ data, positive }) {
  if (!data || data.length < 2) return <div className="w-20 h-6" />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const W = 80, H = 24;
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * W},${H - ((v - min) / range) * (H - 2) - 1}`)
    .join(" ");
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="overflow-visible shrink-0">
      <polyline
        points={pts}
        fill="none"
        stroke={positive ? "#34d399" : "#f87171"}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

const DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "SPY", "TSLA"];

// ── Stock Panel (left sidebar) ─────────────────────────────────────────────
function StockPanel({ open, onToggle }) {
  const [tickers, setTickers] = useState(() => {
    try {
      const saved = localStorage.getItem("silvia_stock_tickers");
      return saved ? JSON.parse(saved) : DEFAULT_TICKERS;
    } catch { return DEFAULT_TICKERS; }
  });
  const [quotes, setQuotes] = useState({});    // symbol → quote data
  const [errors, setErrors] = useState({});    // symbol → error string
  const [loading, setLoading] = useState({});  // symbol → bool
  const [input, setInput] = useState("");
  const [inputError, setInputError] = useState("");

  // Persist tickers to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem("silvia_stock_tickers", JSON.stringify(tickers));
  }, [tickers]);

  // Fetch a single symbol
  const fetchOne = async (sym) => {
    setLoading(p => ({ ...p, [sym]: true }));
    setErrors(p => { const n = { ...p }; delete n[sym]; return n; });
    try {
      const q = await fetchStockQuote(sym);
      setQuotes(p => ({ ...p, [sym]: q }));
    } catch (err) {
      const msg = err.message?.includes("404") ? "Not found" : "Fetch error";
      setErrors(p => ({ ...p, [sym]: msg }));
    } finally {
      setLoading(p => ({ ...p, [sym]: false }));
    }
  };

  // Initial fetch + 60s refresh
  useEffect(() => {
    tickers.forEach(fetchOne);
    const id = setInterval(() => tickers.forEach(fetchOne), 60000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickers.join(",")]);

  const addTicker = () => {
    const sym = input.trim().toUpperCase().replace(/[^A-Z0-9.\-^=]/g, "");
    if (!sym) return;
    if (tickers.includes(sym)) { setInputError("Already tracking"); return; }
    setInputError("");
    setTickers(p => [...p, sym]);
    setInput("");
  };

  const removeTicker = (sym) => {
    setTickers(p => p.filter(s => s !== sym));
    setQuotes(p => { const n = { ...p }; delete n[sym]; return n; });
    setErrors(p => { const n = { ...p }; delete n[sym]; return n; });
  };

  const handleKey = (e) => { if (e.key === "Enter") addTicker(); };

  if (!open) {
    return (
      <button
        onClick={onToggle}
        className="absolute top-20 left-4 z-30 bg-slate-900/80 border border-cyan-500/30 text-cyan-400 text-xs px-2 py-1 rounded hover:bg-slate-800/80 transition-colors"
      >
        Stocks ›
      </button>
    );
  }

  return (
    <aside className="intel-stock-panel absolute top-[76px] left-0 bottom-0 z-20 w-60 bg-slate-950/92 backdrop-blur border-r border-cyan-500/20 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/40 shrink-0">
        <p className="text-[10px] text-slate-500 uppercase tracking-widest">Market Watch</p>
        <button
          onClick={onToggle}
          className="text-slate-600 hover:text-slate-300 text-xs transition-colors"
        >
          ‹ Hide
        </button>
      </div>

      {/* Add ticker input */}
      <div className="px-3 py-2 border-b border-slate-700/40 shrink-0">
        <div className="flex gap-1.5">
          <input
            value={input}
            onChange={e => { setInput(e.target.value.toUpperCase()); setInputError(""); }}
            onKeyDown={handleKey}
            placeholder="TICKER"
            maxLength={10}
            className="flex-1 min-w-0 bg-slate-900 border border-slate-700/60 rounded px-2 py-1 text-[11px] font-mono text-slate-200 placeholder-slate-700 focus:outline-none focus:border-cyan-500/60"
          />
          <button
            onClick={addTicker}
            className="shrink-0 bg-cyan-500/10 border border-cyan-500/40 text-cyan-400 text-[10px] px-2 py-1 rounded hover:bg-cyan-500/20 transition-colors"
          >
            Add
          </button>
        </div>
        {inputError && <p className="text-[9px] text-red-400 mt-1">{inputError}</p>}
      </div>

      {/* Stock list */}
      <div className="flex-1 overflow-y-auto py-1">
        {tickers.map(sym => {
          const q = quotes[sym];
          const err = errors[sym];
          const busy = loading[sym];
          const positive = q ? q.change >= 0 : true;

          return (
            <div key={sym} className="group px-3 py-2 border-b border-slate-800/50 hover:bg-slate-900/40 transition-colors">
              {/* Row 1: symbol + remove + price */}
              <div className="flex items-start justify-between gap-1 mb-1">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] font-bold text-slate-100 font-mono tracking-wide">{sym}</span>
                    {q?.marketState === "PRE" && <span className="text-[8px] text-amber-500/80 border border-amber-500/30 rounded px-0.5">PRE</span>}
                    {q?.marketState === "POST" && <span className="text-[8px] text-blue-400/80 border border-blue-400/30 rounded px-0.5">POST</span>}
                    {q?.marketState === "CLOSED" && <span className="text-[8px] text-slate-600 border border-slate-700/40 rounded px-0.5">CLOSED</span>}
                  </div>
                  {q?.name && (
                    <p className="text-[8px] text-slate-600 leading-tight truncate max-w-[110px]">{q.name}</p>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {busy && !q && (
                    <span className="text-[9px] text-slate-600 animate-pulse">…</span>
                  )}
                  {q && (
                    <div className="text-right">
                      <p className="text-[12px] font-bold text-slate-100 tabular-nums leading-none">{q.price.toFixed(2)}</p>
                      <p className={`text-[9px] tabular-nums leading-none mt-0.5 ${positive ? "text-emerald-400" : "text-red-400"}`}>
                        {positive ? "▲" : "▼"} {Math.abs(q.changePercent).toFixed(2)}%
                      </p>
                    </div>
                  )}
                  {err && (
                    <span className="text-[9px] text-red-500/80">{err}</span>
                  )}
                  <button
                    onClick={() => removeTicker(sym)}
                    className="opacity-0 group-hover:opacity-100 text-slate-700 hover:text-red-400 text-xs transition-all leading-none ml-0.5"
                    title="Remove"
                  >
                    ×
                  </button>
                </div>
              </div>

              {/* Row 2: sparkline + H/L */}
              {q && (
                <div className="flex items-center justify-between gap-1 mt-1">
                  <Sparkline data={q.sparkline} positive={positive} />
                  <div className="text-right text-[8px] text-slate-600 tabular-nums leading-snug">
                    <p>H {q.high?.toFixed(2) ?? "—"}</p>
                    <p>L {q.low?.toFixed(2) ?? "—"}</p>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {tickers.length === 0 && (
          <p className="text-[10px] text-slate-700 text-center py-6">No stocks tracked.<br />Enter a ticker above.</p>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-slate-700/40 shrink-0 text-[9px] text-slate-700 flex justify-between">
        <span>Yahoo Finance · 60s refresh</span>
        <span>{tickers.length} tracked</span>
      </div>
    </aside>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function IntelBoardPage() {
  const [simData, setSimData] = useState(() => getInitialState());
  const [worldEvents, setWorldEvents] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 700);
  const [sidebarTab, setSidebarTab] = useState("intel"); // "intel" | "sim"
  const [categoryFilter, setCategoryFilter] = useState(null);
  const [stockPanelOpen, setStockPanelOpen] = useState(() => window.innerWidth > 700);
  const [liveEarthquakes, setLiveEarthquakes] = useState([]);
  const [liveWeather,     setLiveWeather]     = useState([]);
  const [liveMarkets,     setLiveMarkets]     = useState(null);
  const [clock, setClock] = useState(new Date());
  const stopSimRef = useRef(null);

  const categories = useMemo(() => {
    const cats = new Set(worldEvents.map(e => e.category).filter(Boolean));
    return [...cats].slice(0, 8);
  }, [worldEvents]);

  const filteredEvents = categoryFilter
    ? worldEvents.filter(e => e.category === categoryFilter)
    : worldEvents;

  // Start palantir simulation
  useEffect(() => {
    const stop = startSimulation(setSimData);
    stopSimRef.current = stop;
    return stop;
  }, []);

  // Load CMD-CTR real world events — poll every 20s while assessments are pending, 60s otherwise
  useEffect(() => {
    let timeout;
    async function loadEvents() {
      try {
        const data = await fetchWorldEvents({ live: true });
        const events = Array.isArray(data) ? data : [];
        setWorldEvents(events);
        const hasPending = events.some(e => !e.assessment);
        timeout = setTimeout(loadEvents, hasPending ? 20000 : 60000);
      } catch {
        timeout = setTimeout(loadEvents, 60000);
      }
    }
    loadEvents();
    return () => clearTimeout(timeout);
  }, []);

  // Live earthquakes — USGS, every 5 min
  useEffect(() => {
    const load = () => fetchEarthquakes().then(setLiveEarthquakes).catch(() => {});
    load();
    const id = setInterval(load, 300_000);
    return () => clearInterval(id);
  }, []);

  // Live weather — OpenWeatherMap, every 10 min
  useEffect(() => {
    const load = () => fetchWeather().then(setLiveWeather).catch(() => {});
    load();
    const id = setInterval(load, 600_000);
    return () => clearInterval(id);
  }, []);

  // Live markets — Yahoo Finance, every 60s
  useEffect(() => {
    const load = () => fetchMarkets().then(setLiveMarkets).catch(() => {});
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  // Clock
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const handleEventSelect = (type, data) => setSelectedEvent({ type, data });
  const handleWorldEventSelect = (event) => setSelectedEvent({ type: "worldEvent", data: event });
  const handleCameraSelect = (id) => {
    const cam = publicCameras.find(c => c.id === id);
    if (cam) setSelectedEvent({ type: "camera", data: cam });
  };

  // Prefer live data; fall back to simulation for each layer
  const earthquakes = liveEarthquakes.length > 0 ? liveEarthquakes : simData.earthquakes;
  const weather     = liveWeather.length > 0     ? liveWeather     : simData.weather;
  const markets     = liveMarkets                ? liveMarkets     : (simData.markets || {});

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
          <StatsBadge icon="🌍" label={liveEarthquakes.length > 0 ? "Seismic ●" : "Seismic"} value={earthquakes.length} color="amber" />
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
          earthquakes={earthquakes}
          flights={simData.flights}
          weather={weather}
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

      {/* ── Mobile backdrop (dismisses open sidebars) ── */}
      {(stockPanelOpen || sidebarOpen) && (
        <div
          className="intel-mobile-backdrop"
          onClick={() => { setStockPanelOpen(false); setSidebarOpen(false); }}
        />
      )}

      {/* ── Stock Panel (left) ── */}
      <StockPanel open={stockPanelOpen} onToggle={() => setStockPanelOpen(v => !v)} />

      {/* ── Sidebar Toggle ── */}
      <button
        onClick={() => setSidebarOpen(v => !v)}
        className="absolute top-20 right-4 z-30 bg-slate-900/80 border border-cyan-500/30 text-cyan-400 text-xs px-2 py-1 rounded hover:bg-slate-800/80 transition-colors"
      >
        {sidebarOpen ? "Hide ›" : "‹ Intel"}
      </button>

      {/* ── Right Sidebar ── */}
      {sidebarOpen && (
        <aside className="intel-right-sidebar absolute top-[76px] right-0 bottom-0 z-20 w-72 bg-slate-950/90 backdrop-blur border-l border-cyan-500/20 flex flex-col overflow-hidden">
          <div className="p-3 border-b border-slate-700/40 flex items-center justify-between">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest">Live Intelligence Feed</p>
            <button onClick={() => setSidebarOpen(false)} className="text-slate-600 hover:text-slate-300 text-xs transition-colors">‹ Hide</button>
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

          {/* Tab switcher */}
          <div className="flex shrink-0 border-b border-slate-700/40">
            <button
              onClick={() => setSidebarTab("intel")}
              className={`flex-1 py-1.5 text-[9px] uppercase tracking-widest font-bold transition-colors ${
                sidebarTab === "intel"
                  ? "text-cyan-400 bg-cyan-500/5 border-b-2 border-cyan-500/60"
                  : "text-slate-600 hover:text-slate-400"
              }`}
            >
              World Intel
            </button>
            <button
              onClick={() => setSidebarTab("sim")}
              className={`flex-1 py-1.5 text-[9px] uppercase tracking-widest font-bold transition-colors ${
                sidebarTab === "sim"
                  ? "text-orange-400 bg-orange-500/5 border-b-2 border-orange-500/60"
                  : "text-slate-600 hover:text-slate-400"
              }`}
            >
              Sim Data
            </button>
          </div>

          {/* Feed content */}
          <div className="flex-1 overflow-y-auto p-3">
            {sidebarTab === "intel" ? (
              <div className="space-y-2">
                {/* Category filter chips */}
                {categories.length > 0 && (
                  <div className="flex flex-wrap gap-1 pb-2 border-b border-slate-700/30">
                    <button
                      onClick={() => setCategoryFilter(null)}
                      className={`text-[8px] px-1.5 py-0.5 rounded border uppercase tracking-wide transition-colors ${
                        categoryFilter === null
                          ? "border-cyan-500/60 text-cyan-400 bg-cyan-500/10"
                          : "border-slate-700/40 text-slate-600 hover:text-slate-400"
                      }`}
                    >
                      All
                    </button>
                    {categories.map(cat => (
                      <button
                        key={cat}
                        onClick={() => setCategoryFilter(categoryFilter === cat ? null : cat)}
                        className={`text-[8px] px-1.5 py-0.5 rounded border uppercase tracking-wide transition-colors ${
                          categoryFilter === cat
                            ? "border-cyan-500/60 text-cyan-400 bg-cyan-500/10"
                            : "border-slate-700/40 text-slate-600 hover:text-slate-400"
                        }`}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>
                )}
                <WorldIntelFeed events={filteredEvents} onSelectGlobe={handleWorldEventSelect} />
              </div>
            ) : (
              <SimFeed
                threats={simData.threats}
                earthquakes={earthquakes}
                radiation={simData.radiation}
              />
            )}
          </div>

          {/* Status footer */}
          <div className="p-3 border-t border-slate-700/40 flex justify-between text-[9px] text-slate-600">
            {sidebarTab === "intel" ? (
              <>
                <span>⬤ {filteredEvents.length} EVENTS</span>
                <span className={worldEvents.some(e => !e.assessment) ? "text-amber-600" : "text-teal-700"}>
                  ⬤ {worldEvents.filter(e => e.assessment).length}/{worldEvents.length} ASSESSED
                </span>
              </>
            ) : (
              <>
                <span className={liveEarthquakes.length > 0 ? "text-teal-700" : ""}>
                  {liveEarthquakes.length > 0 ? "● SEISMIC LIVE" : "○ SIM SEISMIC"}
                </span>
                <span className={liveWeather.length > 0 ? "text-teal-700" : ""}>
                  {liveWeather.length > 0 ? "● WEATHER LIVE" : "○ SIM WEATHER"}
                </span>
              </>
            )}
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
