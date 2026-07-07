import { useState, useEffect, useRef, useCallback } from "react";
import { liveStreams } from "../../data/mediaChannels";

// Validate a YouTube ID by checking its thumbnail returns 200 (not the default placeholder)
async function checkFeedHealth(youtubeId) {
  try {
    const r = await fetch(`https://img.youtube.com/vi/${youtubeId}/mqdefault.jpg`, { mode: "no-cors" });
    return true;
  } catch {
    return false;
  }
}

function YouTubeEmbed({ videoId, title }) {
  if (!videoId) return null;
  return (
    <iframe
      src={`https://www.youtube.com/embed/${videoId}?autoplay=1&mute=1&controls=1&modestbranding=1&rel=0&playsinline=1`}
      title={title}
      className="iv4-media-iframe"
      allow="autoplay; encrypted-media; picture-in-picture"
      allowFullScreen
    />
  );
}

function SourceButton({ stream, active, onClick }) {
  return (
    <button
      className={`iv4-src-btn${active ? " iv4-src-btn--active" : ""}`}
      onClick={() => onClick(stream)}
    >
      <img
        src={`https://img.youtube.com/vi/${stream.youtubeId}/mqdefault.jpg`}
        alt=""
        className="iv4-src-thumb"
        loading="lazy"
      />
      <div className="iv4-src-info">
        <span className="iv4-src-name">{stream.name}</span>
        <span className="iv4-src-live">● LIVE</span>
      </div>
    </button>
  );
}

function CameraButton({ cam, active, onClick }) {
  return (
    <button
      className={`iv4-src-btn${active ? " iv4-src-btn--active" : ""}`}
      onClick={() => onClick(cam)}
      title={cam.location}
    >
      <img
        src={`https://img.youtube.com/vi/${cam.youtubeId}/mqdefault.jpg`}
        alt=""
        className="iv4-src-thumb"
        loading="lazy"
      />
      <div className="iv4-src-info">
        <span className="iv4-src-name">{cam.name}</span>
        <span className="iv4-src-loc">{cam.location}</span>
      </div>
    </button>
  );
}

export default function IntelLiveMedia({ cameras = [], externalFeed = null }) {
  const [healthyStreams, setHealthyStreams] = useState(liveStreams);
  const [active, setActive] = useState(null);
  const [mode, setMode] = useState("news");
  const [autoRotate, setAutoRotate] = useState(true);
  const rotateRef = useRef(null);

  // Health check on mount — validate all streams, hide failures
  useEffect(() => {
    let cancelled = false;
    async function validate() {
      const results = await Promise.all(
        liveStreams.map(async (s) => {
          const ok = await checkFeedHealth(s.youtubeId);
          return ok ? s : null;
        })
      );
      if (cancelled) return;
      const healthy = results.filter(Boolean);
      setHealthyStreams(healthy);
      if (!active && healthy.length > 0) {
        const firstNews = healthy.find((s) => s.category === "world") || healthy[0];
        setActive(firstNews);
      }
    }
    validate();
    // Re-validate every 10 minutes
    const id = setInterval(validate, 600000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const newsStreams = healthyStreams.filter((s) => s.category === "world");
  const spaceStreams = healthyStreams.filter((s) => s.category === "space");

  // External camera from globe click
  useEffect(() => {
    if (externalFeed?.youtubeId) {
      setActive(externalFeed);
      setMode("cams");
      setAutoRotate(false);
    }
  }, [externalFeed]);

  // Auto-rotate news every 2 minutes
  useEffect(() => {
    if (!autoRotate || mode !== "news" || newsStreams.length === 0) {
      clearInterval(rotateRef.current);
      return;
    }
    rotateRef.current = setInterval(() => {
      setActive((prev) => {
        const idx = newsStreams.findIndex((s) => s.id === prev?.id);
        return newsStreams[(idx + 1) % newsStreams.length];
      });
    }, 120000);
    return () => clearInterval(rotateRef.current);
  }, [autoRotate, mode, newsStreams.length]);

  const selectStream = useCallback((s) => {
    setActive(s);
    setAutoRotate(false);
  }, []);

  const selectCamera = useCallback((cam) => {
    setActive(cam);
    setMode("cams");
    setAutoRotate(false);
  }, []);

  if (healthyStreams.length === 0 && cameras.length === 0) return null;

  return (
    <div className="iv4-livemedia">
      <div className="iv4-livemedia-head">
        <div className="iv4-livemedia-title-row">
          <span className="iv4-section-title" style={{ fontSize: 11 }}>LIVE MEDIA</span>
          {active && <span className="iv4-media-live-indicator">● LIVE</span>}
          <span className="iv4-livemedia-now">{active?.name || ""}</span>
        </div>
        <div className="iv4-livemedia-modes">
          {newsStreams.length > 0 && (
            <button
              className={`iv4-mode-btn${mode === "news" ? " iv4-mode-btn--on" : ""}`}
              onClick={() => { setMode("news"); setActive(newsStreams[0]); setAutoRotate(true); }}
            >
              NEWS ({newsStreams.length})
            </button>
          )}
          {spaceStreams.length > 0 && (
            <button
              className={`iv4-mode-btn${mode === "space" ? " iv4-mode-btn--on" : ""}`}
              onClick={() => { setMode("space"); setActive(spaceStreams[0]); setAutoRotate(false); }}
            >
              SPACE
            </button>
          )}
          {cameras.length > 0 && (
            <button
              className={`iv4-mode-btn${mode === "cams" ? " iv4-mode-btn--on" : ""}`}
              onClick={() => setMode("cams")}
            >
              WEBCAMS
            </button>
          )}
          <span className="iv4-livemedia-sep" />
          <button
            className={`iv4-media-ctrl${autoRotate ? " iv4-media-ctrl--on" : ""}`}
            onClick={() => setAutoRotate((v) => !v)}
          >
            {autoRotate ? "⟳ AUTO" : "⏸ HOLD"}
          </button>
        </div>
      </div>

      <div className="iv4-livemedia-body">
        <div className="iv4-media-player">
          <YouTubeEmbed videoId={active?.youtubeId} title={active?.name || ""} />
        </div>

        <div className="iv4-src-list">
          {mode === "news" && newsStreams.map((s) => (
            <SourceButton key={s.id} stream={s} active={active?.id === s.id} onClick={selectStream} />
          ))}
          {mode === "space" && spaceStreams.map((s) => (
            <SourceButton key={s.id} stream={s} active={active?.id === s.id} onClick={selectStream} />
          ))}
          {mode === "cams" && cameras.slice(0, 30).map((cam) => (
            <CameraButton key={cam.id} cam={cam} active={active?.id === cam.id} onClick={selectCamera} />
          ))}
        </div>
      </div>
    </div>
  );
}
