import { useEffect, useRef, useState } from "react";
import { fetchDesktopApps, fetchLocations, fetchRecentFiles, openApp, openLocation, searchFiles } from "../../lib/api";

const CATEGORY_ICON = {
  development: "◈",
  cad: "⬡",
  electronics: "⬢",
  browser: "◉",
  media: "▶",
  system: "◻",
  general: "○",
};

function StatusDot({ ok }) {
  return <span className={`files-dot files-dot--${ok ? "ok" : "miss"}`} />;
}

function LocationRow({ loc, onOpen }) {
  return (
    <div className="files-row">
      <StatusDot ok={loc.exists} />
      <span className="files-row__name" title={loc.path}>{loc.name}</span>
      <span className="files-row__desc">{loc.description}</span>
      <button
        className="files-btn"
        onClick={() => onOpen(loc.name)}
        disabled={!loc.exists}
        title={loc.exists ? `Open ${loc.path}` : "Path not found on disk"}
      >
        Open
      </button>
    </div>
  );
}

function AppRow({ app, onLaunch }) {
  const icon = CATEGORY_ICON[app.category] || "○";
  return (
    <div className="files-row">
      <StatusDot ok={app.available} />
      <span className="files-app-icon">{icon}</span>
      <span className="files-row__name">{app.name}</span>
      <span className="files-row__desc">{app.category}</span>
      <button
        className="files-btn"
        onClick={() => onLaunch(app.name)}
        disabled={!app.available}
        title={app.available ? `Launch ${app.name}` : "Not available on this machine"}
      >
        Launch
      </button>
    </div>
  );
}

function FileRow({ file }) {
  return (
    <div className="files-row files-row--file">
      <span className="files-row__name" title={file.path}>{file.name}</span>
      <span className="files-row__meta">{file.location}</span>
      <span className="files-row__meta">{file.modified}</span>
      <span className="files-row__meta">{file.size}</span>
    </div>
  );
}

export default function FilesPanel() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("locations"); // "locations" | "apps" | "search"

  const [locations, setLocations] = useState(null);
  const [apps, setApps] = useState(null);
  const [recentFiles, setRecentFiles] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchExt, setSearchExt] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [feedback, setFeedback] = useState("");

  const searchRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    if (tab === "locations" && !locations) {
      fetchLocations().then(setLocations).catch(() => setLocations([]));
    }
    if (tab === "apps" && !apps) {
      fetchDesktopApps().then(setApps).catch(() => setApps([]));
    }
    if (tab === "recent" && !recentFiles) {
      fetchRecentFiles().then((data) => setRecentFiles(data.results || [])).catch(() => setRecentFiles([]));
    }
  }, [open, tab]);

  function flash(msg) {
    setFeedback(msg);
    setTimeout(() => setFeedback(""), 3000);
  }

  async function handleOpenLocation(name) {
    try {
      await openLocation(name);
      flash(`Opened ${name}`);
    } catch {
      flash(`Failed to open ${name}`);
    }
  }

  async function handleLaunchApp(name) {
    try {
      await openApp(name);
      flash(`Launched ${name}`);
    } catch {
      flash(`Failed to launch ${name}`);
    }
  }

  async function handleSearch(e) {
    e.preventDefault();
    if (!searchQuery && !searchExt) return;
    setSearching(true);
    setSearchResults(null);
    try {
      const data = await searchFiles({ query: searchQuery, extension: searchExt });
      setSearchResults(data.results || []);
      if ((data.results || []).length === 0) flash("No files found.");
    } catch {
      flash("Search failed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <section className="files-panel">
      <button
        className={`files-panel__header${open ? " files-panel__header--open" : ""}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="files-panel__chevron">{open ? "▾" : "▸"}</span>
        <span className="files-panel__title">Files &amp; Applications</span>
      </button>

      {open && (
        <div className="files-panel__body">
          {feedback && <div className="files-feedback">{feedback}</div>}

          <div className="files-tabs">
            {["locations", "recent", "apps", "search"].map((t) => (
              <button
                key={t}
                className={`files-tab${tab === t ? " files-tab--active" : ""}`}
                onClick={() => setTab(t)}
              >
                {t === "locations" ? "Folders" : t === "recent" ? "Recent" : t === "apps" ? "Apps" : "Search"}
              </button>
            ))}
          </div>

          {tab === "locations" && (
            <div className="files-section">
              {locations === null && <div className="files-loading">Loading…</div>}
              {locations !== null && locations.length === 0 && (
                <div className="files-empty">No trusted locations registered.</div>
              )}
              {(locations || []).map((loc) => (
                <LocationRow key={loc.id} loc={loc} onOpen={handleOpenLocation} />
              ))}
            </div>
          )}

          {tab === "recent" && (
            <div className="files-section">
              {recentFiles === null && <div className="files-loading">Loading...</div>}
              {recentFiles !== null && recentFiles.length === 0 && (
                <div className="files-empty">No recent files found.</div>
              )}
              {(recentFiles || []).map((file, i) => (
                <FileRow key={`${file.path}-${i}`} file={file} />
              ))}
            </div>
          )}

          {tab === "apps" && (
            <div className="files-section">
              {apps === null && <div className="files-loading">Loading…</div>}
              {apps !== null && apps.length === 0 && (
                <div className="files-empty">No apps registered.</div>
              )}
              {(apps || []).map((app) => (
                <AppRow key={app.id} app={app} onLaunch={handleLaunchApp} />
              ))}
            </div>
          )}

          {tab === "search" && (
            <div className="files-section">
              <form className="files-search-form" onSubmit={handleSearch}>
                <input
                  ref={searchRef}
                  className="files-search-input"
                  placeholder="Filename or keyword…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <input
                  className="files-search-input files-search-input--ext"
                  placeholder="ext (stl, pdf…)"
                  value={searchExt}
                  onChange={(e) => setSearchExt(e.target.value)}
                />
                <button className="files-btn files-btn--search" type="submit" disabled={searching}>
                  {searching ? "…" : "Find"}
                </button>
              </form>

              {searching && <div className="files-loading">Searching…</div>}

              {searchResults !== null && searchResults.length === 0 && (
                <div className="files-empty">No files found.</div>
              )}

              {(searchResults || []).map((f, i) => (
                <FileRow key={i} file={f} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
