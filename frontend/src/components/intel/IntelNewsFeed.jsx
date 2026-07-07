import { useState } from "react";

const CATEGORY_TABS = ["ALL", "WORLD", "AI / TECH", "ENGINEERING", "CYBER", "SCIENCE", "BUSINESS"];

const SOURCE_STYLE = {
  "BBC News":          { color: "#bb1919" },
  "Reuters":           { color: "#ff6600" },
  "The Guardian":      { color: "#0084c6" },
  "Sky News":          { color: "#9b1b30" },
  "NPR World":        { color: "#2b7bb9" },
  "Ars Technica":      { color: "#ff4e00" },
  "The Verge":         { color: "#e5127d" },
  "Hacker News":       { color: "#ff6600" },
  "TechCrunch":        { color: "#0a9e01" },
  "VentureBeat":       { color: "#8b00ff" },
  "Hackaday":          { color: "#d42029" },
  "IEEE Spectrum":     { color: "#00629b" },
  "New Atlas":         { color: "#00b4d8" },
  "Raspberry Pi":      { color: "#c51a4a" },
  "Arduino":           { color: "#00979d" },
  "Tom's Hardware":    { color: "#e00000" },
  "The Hacker News":   { color: "#2b2b2b" },
  "BleepingComputer":  { color: "#4a90d9" },
  "Krebs on Security": { color: "#333333" },
  "Dark Reading":      { color: "#1a1a2e" },
  "Science Daily":     { color: "#0072bc" },
  "Phys.org":          { color: "#2c5f8a" },
  "Space.com":         { color: "#1b1464" },
  "NASA":              { color: "#0b3d91" },
  "default":           { color: "#00e5ff" },
};

const CAT_MAP = {
  politics:    { tab: "WORLD",       color: "#00e5ff" },
  conflict:    { tab: "WORLD",       color: "#ff3b3b" },
  general:     { tab: "WORLD",       color: "#00e5ff" },
  tech:        { tab: "AI / TECH",   color: "#60a5fa" },
  science:     { tab: "SCIENCE",     color: "#c084fc" },
  engineering: { tab: "ENGINEERING", color: "#f5a623" },
  cyber:       { tab: "CYBER",       color: "#ff3b3b" },
  economy:     { tab: "BUSINESS",    color: "#f5a623" },
  economics:   { tab: "BUSINESS",    color: "#f5a623" },
  health:      { tab: "SCIENCE",     color: "#4ade80" },
  environment: { tab: "WORLD",       color: "#4ade80" },
  disaster:    { tab: "WORLD",       color: "#ff3b3b" },
  culture:     { tab: "WORLD",       color: "#f5a623" },
  sports:      { tab: "WORLD",       color: "#60a5fa" },
};

function timeAgo(ts) {
  if (!ts) return "";
  const ms = typeof ts === "number" ? ts : parseInt(ts, 10);
  if (isNaN(ms) || ms === 0) {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "";
    const diff = Date.now() - d.getTime();
    if (diff < 60000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }
  const diff = Date.now() - ms;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

function getTab(ev) {
  const cat = (ev.category || "general").toLowerCase();
  return (CAT_MAP[cat] || CAT_MAP.general).tab;
}

function tabMatch(ev, tab) {
  if (tab === "ALL") return true;
  return getTab(ev) === tab;
}

function openArticle(ev) {
  const url = ev.source_url || ev.url;
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

function NewsCard({ event }) {
  const src = SOURCE_STYLE[event.source_name] || SOURCE_STYLE.default;
  const cat = CAT_MAP[event.category] || CAT_MAP.general;
  const sev = (event.board_priority || "low").toLowerCase();
  const isLive = sev === "critical" || sev === "high";
  const hasUrl = !!(event.source_url || event.url);

  return (
    <div
      className={`iv4-news-card${hasUrl ? "" : " iv4-news-card--nolink"}`}
      onClick={() => openArticle(event)}
      title={hasUrl ? "Click to open article" : "No source URL available"}
    >
      <div className="iv4-news-card-top">
        <div className="iv4-news-source-row">
          {isLive && <span className="iv4-news-live">LIVE</span>}
          <span className="iv4-news-source" style={{ color: src.color }}>
            {event.source_name || "Source"}
          </span>
          <span className="iv4-news-time">
            {timeAgo(event.published_at || event.updated_at)}
          </span>
        </div>
        <span className="iv4-news-cat" style={{ color: cat.color, borderColor: cat.color + "40" }}>
          {cat.tab}
        </span>
      </div>

      <p className="iv4-news-headline">{event.title}</p>

      {event.summary && (
        <p className="iv4-news-summary">{event.summary}</p>
      )}

      {hasUrl && (
        <div className="iv4-news-footer">
          <span className="iv4-news-open">READ ARTICLE ↗</span>
        </div>
      )}
    </div>
  );
}

export default function IntelNewsFeed({ events = [] }) {
  const [activeTab, setActiveTab] = useState("ALL");

  const filtered = events.filter((e) => {
    if (!tabMatch(e, activeTab)) return false;
    return true;
  });

  const tabCounts = {};
  CATEGORY_TABS.forEach((t) => {
    tabCounts[t] = t === "ALL" ? events.length : events.filter((e) => tabMatch(e, t)).length;
  });

  return (
    <div className="iv4-newsfeed">
      <div className="iv4-newsfeed-head">
        <span className="iv4-section-title" style={{ fontSize: 11 }}>‹ LIVE NEWS FEED</span>
        <div className="iv4-newsfeed-tabs">
          {CATEGORY_TABS.map((t) => (
            <button
              key={t}
              className={`iv4-newsfeed-tab${activeTab === t ? " iv4-newsfeed-tab--on" : ""}${tabCounts[t] === 0 ? " iv4-newsfeed-tab--empty" : ""}`}
              onClick={() => setActiveTab(t)}
            >
              {t}
              {tabCounts[t] > 0 && <span className="iv4-newsfeed-tab-ct">{tabCounts[t]}</span>}
            </button>
          ))}
        </div>
      </div>
      <div className="iv4-newsfeed-scroll">
        {filtered.length === 0 && (
          <p className="iv4-empty" style={{ padding: "16px 20px" }}>
            No events in this category yet — feeds are loading
          </p>
        )}
        {filtered.slice(0, 30).map((ev) => (
          <NewsCard key={ev.id} event={ev} />
        ))}
      </div>
    </div>
  );
}
