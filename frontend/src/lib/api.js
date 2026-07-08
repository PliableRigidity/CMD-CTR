// Use the same host the browser connected to — works for localhost and Tailscale/LAN
const _host = window.location.hostname;
const API_BASE = `http://${_host}:8001/api`;
const WS_BASE  = `ws://${_host}:8001/api/ws/events`;
const _WS_WAKE_BASE = `ws://${_host}:8001/api/ws/wake`;

// ---------------------------------------------------------------------------
// API key helpers — key stored in localStorage under "silvia_api_key"
// ---------------------------------------------------------------------------

export function getApiKey() {
  return localStorage.getItem("silvia_api_key") || "";
}

export function setApiKey(key) {
  if (key) localStorage.setItem("silvia_api_key", key);
  else localStorage.removeItem("silvia_api_key");
}

let _on401Handler = null;

export function on401(handler) {
  _on401Handler = handler;
}

function _apiFetch(url, opts = {}) {
  const key = getApiKey();
  const headers = key ? { ...(opts.headers || {}), "X-API-Key": key } : (opts.headers || {});
  return fetch(url, { ...opts, headers }).then((res) => {
    if (res.status === 401 && _on401Handler) _on401Handler();
    return res;
  });
}

export function getWakeWsUrl() {
  const key = getApiKey();
  return key ? `${_WS_WAKE_BASE}?api_key=${encodeURIComponent(key)}` : _WS_WAKE_BASE;
}

async function readJson(response) {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Request failed.");
  }
  return response.json();
}

export async function fetchMode() {
  return readJson(await _apiFetch(`${API_BASE}/mode`));
}

export async function setMode(mode) {
  return readJson(
    await _apiFetch(`${API_BASE}/mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),
  );
}

export async function sendChat(payload) {
  return readJson(
    await _apiFetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function sendChatStream(payload, onChunk) {
  const response = await _apiFetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const raw = line.slice(6).trim();
        if (raw) {
          try { onChunk(JSON.parse(raw)); } catch { /* skip malformed */ }
        }
      }
    }
  }
}

export async function sendDecision(payload) {
  return readJson(
    await _apiFetch(`${API_BASE}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchActions() {
  return readJson(await _apiFetch(`${API_BASE}/actions`));
}

export async function fetchMissions() {
  return readJson(await _apiFetch(`${API_BASE}/missions`));
}

export async function executeActionAlias(target) {
  return readJson(
    await _apiFetch(`${API_BASE}/actions/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    }),
  );
}

export async function openAppAction(actionId, args = []) {
  return readJson(
    await _apiFetch(`${API_BASE}/actions/open-app`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: actionId, args }),
    }),
  );
}

export async function openUrlAction(target) {
  return readJson(
    await _apiFetch(`${API_BASE}/actions/open-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    }),
  );
}

export async function fetchDevices() {
  return readJson(await _apiFetch(`${API_BASE}/devices`));
}

export async function fetchStockQuote(symbol) {
  return readJson(await _apiFetch(`${API_BASE}/world/stock/${encodeURIComponent(symbol)}`));
}

export async function fetchEarthquakes() {
  return readJson(await _apiFetch(`${API_BASE}/world/earthquakes`));
}

export async function fetchWeather() {
  return readJson(await _apiFetch(`${API_BASE}/world/weather`));
}

export async function fetchMarkets() {
  return readJson(await _apiFetch(`${API_BASE}/world/markets`));
}

export async function fetchWorldEvents({ live = true, category, country } = {}) {
  const query = new URLSearchParams();
  if (live) query.set("live", "true");
  if (category) query.set("category", category);
  if (country) query.set("country", country);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return readJson(await _apiFetch(`${API_BASE}/world/events${suffix}`));
}

export async function fetchVoiceStatus() {
  return readJson(await _apiFetch(`${API_BASE}/voice/status`));
}

export async function updateVoiceState(payload) {
  return readJson(
    await _apiFetch(`${API_BASE}/voice/state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchRoute(payload) {
  return readJson(
    await _apiFetch(`${API_BASE}/maps/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchLogs() {
  return readJson(await _apiFetch(`${API_BASE}/events/logs`));
}

export async function fetchAudioState() {
  return readJson(await _apiFetch(`${API_BASE}/system/audio`));
}

async function postSystem(path, body) {
  return readJson(
    await _apiFetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }),
  );
}

export async function setAudioVolume(volumePercent) {
  return postSystem("/system/audio/set", { volume_percent: volumePercent });
}

export async function volumeUp() {
  return postSystem("/system/audio/up");
}

export async function volumeDown() {
  return postSystem("/system/audio/down");
}

export async function toggleMute() {
  return postSystem("/system/audio/mute");
}

export async function mediaPlayPause() {
  return postSystem("/system/media/play-pause");
}

export async function mediaNext() {
  return postSystem("/system/media/next");
}

export async function mediaPrevious() {
  return postSystem("/system/media/previous");
}

export function createEventsSocket() {
  const key = getApiKey();
  const url = key ? `${WS_BASE}?api_key=${encodeURIComponent(key)}` : WS_BASE;
  return new WebSocket(url);
}

// ---------------------------------------------------------------------------
// Memory API
// ---------------------------------------------------------------------------

export async function fetchHistory(sessionId = "default-session", limit = 100) {
  return readJson(
    await _apiFetch(`${API_BASE}/memory/history?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`)
  );
}

export async function clearHistory(sessionId = "default-session") {
  return readJson(
    await _apiFetch(`${API_BASE}/memory/history?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    })
  );
}

export async function fetchFacts() {
  return readJson(await _apiFetch(`${API_BASE}/memory/facts`));
}

export async function saveFact(key, value) {
  return readJson(
    await _apiFetch(`${API_BASE}/memory/facts?key=${encodeURIComponent(key)}&value=${encodeURIComponent(value)}`, {
      method: "POST",
    })
  );
}

const _MIME_EXT = {
  "audio/webm": "webm", "video/webm": "webm",
  "audio/ogg": "ogg", "audio/wav": "wav",
  "audio/mpeg": "mp3", "audio/mp4": "mp4",
};

function _mimeToExt(mimeType) {
  const base = (mimeType || "").split(";")[0].trim().toLowerCase();
  return _MIME_EXT[base] || "webm";
}

export async function transcribeAudio(audioBlob, mimeType) {
  const ext = _mimeToExt(mimeType || audioBlob.type);
  const form = new FormData();
  form.append("audio", audioBlob, `recording.${ext}`);
  const response = await _apiFetch(`${API_BASE}/voice/transcribe`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function fetchVoiceDiagnostics() {
  return readJson(await _apiFetch(`${API_BASE}/voice/diagnostics`));
}

export async function synthesizeSpeech(text) {
  const response = await _apiFetch(`${API_BASE}/voice/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.arrayBuffer();
}

// ---------------------------------------------------------------------------
// Node Registry
// ---------------------------------------------------------------------------

export async function fetchNodes() {
  return readJson(await _apiFetch(`${API_BASE}/nodes`));
}

export async function createNode(data) {
  return readJson(
    await _apiFetch(`${API_BASE}/nodes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function deleteNode(id) {
  const res = await _apiFetch(`${API_BASE}/nodes/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function updateNode(id, data) {
  return readJson(
    await _apiFetch(`${API_BASE}/nodes/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function updateNodeMetrics(id, metrics) {
  return readJson(
    await _apiFetch(`${API_BASE}/nodes/${id}/metrics`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metrics),
    }),
  );
}

export async function probeNode(id) {
  return readJson(
    await _apiFetch(`${API_BASE}/nodes/${id}/probe`, {
      method: "POST",
    }),
  );
}

export async function verifyNode(id) {
  return readJson(
    await _apiFetch(`${API_BASE}/nodes/${id}/verify`, {
      method: "POST",
    }),
  );
}

// ---------------------------------------------------------------------------
// Watch Officer
// ---------------------------------------------------------------------------

export async function fetchWatchAlerts() {
  return readJson(await _apiFetch(`${API_BASE}/watch`));
}

export async function createWatchAlert(data) {
  return readJson(
    await _apiFetch(`${API_BASE}/watch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function dismissWatchAlert(id) {
  return readJson(
    await _apiFetch(`${API_BASE}/watch/${id}/dismiss`, { method: "POST" }),
  );
}

// ---------------------------------------------------------------------------
// Telemetry History
// ---------------------------------------------------------------------------

export async function fetchNodeTelemetryHistory(nodeId, hours = 24) {
  return readJson(await _apiFetch(`${API_BASE}/nodes/${encodeURIComponent(nodeId)}/telemetry/history?hours=${hours}`));
}

// ---------------------------------------------------------------------------
// Scheduled Tasks
// ---------------------------------------------------------------------------

export async function fetchScheduledTasks() {
  return readJson(await _apiFetch(`${API_BASE}/scheduled-tasks`));
}

export async function createScheduledTask(data) {
  return readJson(
    await _apiFetch(`${API_BASE}/scheduled-tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function updateScheduledTask(id, data) {
  return readJson(
    await _apiFetch(`${API_BASE}/scheduled-tasks/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function deleteScheduledTask(id) {
  const res = await _apiFetch(`${API_BASE}/scheduled-tasks/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export async function fetchProjects(status = "") {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return readJson(await _apiFetch(`${API_BASE}/projects${qs}`));
}

export async function createProject(data) {
  return readJson(await _apiFetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function updateProject(id, data) {
  return readJson(await _apiFetch(`${API_BASE}/projects/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function touchProject(id) {
  return readJson(await _apiFetch(`${API_BASE}/projects/${id}/touch`, { method: "POST" }));
}

export async function deleteProject(id) {
  const res = await _apiFetch(`${API_BASE}/projects/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

// ---------------------------------------------------------------------------
// Mission Control
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Service Registry (Phase 10)
// ---------------------------------------------------------------------------

export async function fetchNodeServices(nodeId) {
  const qs = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
  return readJson(await _apiFetch(`${API_BASE}/services${qs}`));
}

export async function fetchService(serviceId) {
  return readJson(await _apiFetch(`${API_BASE}/services/${encodeURIComponent(serviceId)}`));
}

export async function createNodeService(nodeId, data) {
  return readJson(await _apiFetch(`${API_BASE}/nodes/${encodeURIComponent(nodeId)}/services`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function updateService(serviceId, data) {
  return readJson(await _apiFetch(`${API_BASE}/services/${encodeURIComponent(serviceId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function deleteService(serviceId) {
  return _apiFetch(`${API_BASE}/services/${encodeURIComponent(serviceId)}`, { method: "DELETE" });
}

export async function addCapability(serviceId, data) {
  return readJson(await _apiFetch(`${API_BASE}/services/${encodeURIComponent(serviceId)}/capabilities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function searchCapabilities(capability, node = null, runningOnly = false) {
  const params = new URLSearchParams({ capability });
  if (node) params.set("node", node);
  if (runningOnly) params.set("running_only", "true");
  return readJson(await _apiFetch(`${API_BASE}/capabilities/search?${params}`));
}

export async function executeCapability(capability, serviceId = null, args = {}, nodeName = null) {
  return readJson(await _apiFetch(`${API_BASE}/capabilities/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ capability, service_id: serviceId, node_name: nodeName, args }),
  }));
}

// UI-safe variant — always resolves (never throws); returns {ok, summary, error}
export async function executeCapabilityUI(capability, serviceId = null, args = {}, nodeName = null) {
  try {
    const result = await readJson(await _apiFetch(`${API_BASE}/capabilities/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capability, service_id: serviceId, node_name: nodeName, args }),
    }));
    return { ok: true, summary: result.summary || "Done", ...result };
  } catch (e) {
    let msg = e.message || "Execution failed";
    try { msg = JSON.parse(msg).detail || msg; } catch {}
    return { ok: false, summary: msg };
  }
}

// ── Fleet Management (Phase 13B) ─────────────────────────────────────────────

export async function fetchFleetStatus() {
  const r = await _apiFetch(`${API_BASE}/fleet/status`);
  return readJson(r);
}

export async function fetchFleetOffline() {
  const r = await _apiFetch(`${API_BASE}/fleet/offline`);
  return readJson(r);
}

export async function fetchFleetUnhealthy() {
  const r = await _apiFetch(`${API_BASE}/fleet/unhealthy`);
  return readJson(r);
}

export async function fetchFleetGroups() {
  const r = await _apiFetch(`${API_BASE}/fleet/groups`);
  return readJson(r);
}

export async function fetchFleetNodes(filterType = "all", filterValue = "") {
  const params = new URLSearchParams({ filter_type: filterType, filter_value: filterValue });
  const r = await _apiFetch(`${API_BASE}/fleet/nodes?${params}`);
  return readJson(r);
}

export async function fleetAction(capability, filterType, filterValue, serviceName = null, args = {}, dryRun = true) {
  const r = await _apiFetch(`${API_BASE}/fleet/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      capability,
      filter_type: filterType,
      filter_value: filterValue,
      service_name: serviceName,
      args,
      dry_run: dryRun,
    }),
  });
  return readJson(r);
}

// ── Project Intelligence (Phase 14A) ──────────────────────────────────────────

export async function fetchProjectBriefing(project) {
  return readJson(await _apiFetch(`${API_BASE}/projects/intelligence/${encodeURIComponent(project)}`));
}

export async function fetchProjectBlockers(project) {
  return readJson(await _apiFetch(`${API_BASE}/projects/intelligence/${encodeURIComponent(project)}/blockers`));
}

export async function fetchProjectReadiness(project) {
  return readJson(await _apiFetch(`${API_BASE}/projects/intelligence/${encodeURIComponent(project)}/readiness`));
}

export async function fetchProjectsUsing(component) {
  return readJson(await _apiFetch(`${API_BASE}/projects/using/${encodeURIComponent(component)}`));
}

export async function fetchBlockedProjects() {
  return readJson(await _apiFetch(`${API_BASE}/projects/blocked`));
}

export async function fetchStartableProjects() {
  return readJson(await _apiFetch(`${API_BASE}/projects/startable`));
}

export async function fetchKnowledgeEntities(type = "") {
  const q = type ? `?type=${encodeURIComponent(type)}` : "";
  return readJson(await _apiFetch(`${API_BASE}/knowledge/entities${q}`));
}

export async function addKnowledgeRelationship(fromName, fromType, toName, toType, relType) {
  const r = await _apiFetch(`${API_BASE}/knowledge/relationships`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from_name: fromName, from_type: fromType, to_name: toName, to_type: toType, rel_type: relType }),
  });
  return readJson(r);
}

export async function fetchKnowledgeGraph() {
  return readJson(await _apiFetch(`${API_BASE}/knowledge/graph`));
}

export async function fetchProjectGraph(project) {
  return readJson(await _apiFetch(`${API_BASE}/knowledge/graph/project/${encodeURIComponent(project)}`));
}

export async function rebuildKnowledgeGraph() {
  return readJson(await _apiFetch(`${API_BASE}/knowledge/rebuild`, { method: "POST" }));
}

// ── Engineering Memory (Phase 14C) ────────────────────────────────────────────

export async function fetchMemoryProjects() {
  return readJson(await _apiFetch(`${API_BASE}/memory/projects`));
}

export async function fetchProjectMemory(project = "") {
  const url = project
    ? `${API_BASE}/memory/projects/${encodeURIComponent(project)}`
    : `${API_BASE}/memory/recent?days=30`;
  return readJson(await _apiFetch(url));
}

export async function fetchProjectTimeline(project) {
  return readJson(await _apiFetch(`${API_BASE}/memory/timeline/${encodeURIComponent(project)}`));
}

export async function recordMemory(data) {
  return readJson(await _apiFetch(`${API_BASE}/memory/record`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function importBrain63Memory(project = "") {
  const params = project ? `?project=${encodeURIComponent(project)}` : "";
  return readJson(await _apiFetch(`${API_BASE}/memory/import${params}`, { method: "POST" }));
}

// ── Observability (Phase 13C) ─────────────────────────────────────────────────

export async function fetchRecentActions(limit = 20, node = "", status = "") {
  const params = new URLSearchParams({ limit });
  if (node)   params.set("node", node);
  if (status) params.set("status", status);
  return readJson(await _apiFetch(`${API_BASE}/observability/recent?${params}`));
}

export async function fetchFailures(limit = 20) {
  return readJson(await _apiFetch(`${API_BASE}/observability/failures?limit=${limit}`));
}

export async function fetchPlannerTrace(limit = 10) {
  return readJson(await _apiFetch(`${API_BASE}/observability/planner?limit=${limit}`));
}

export async function fetchCapabilityHealth() {
  return readJson(await _apiFetch(`${API_BASE}/observability/health`));
}

// ── Productivity (Phase 12G) — Gmail, Calendar, Contacts ─────────────────────

export async function fetchProductivityAuthStatus() {
  return readJson(await _apiFetch(`${API_BASE}/productivity/auth/status`));
}

export function getGoogleAuthUrl() {
  return `${API_BASE}/productivity/auth/google`;
}

export async function disconnectGoogle() {
  await _apiFetch(`${API_BASE}/productivity/auth/google`, { method: "DELETE" });
}

export async function fetchInbox(search = "", limit = 10) {
  const params = new URLSearchParams({ limit });
  if (search) params.set("search", search);
  return readJson(await _apiFetch(`${API_BASE}/productivity/gmail/inbox?${params}`));
}

export async function searchEmails(q, limit = 10) {
  return readJson(await _apiFetch(`${API_BASE}/productivity/gmail/search?q=${encodeURIComponent(q)}&limit=${limit}`));
}

export async function fetchCalendarToday() {
  return readJson(await _apiFetch(`${API_BASE}/productivity/calendar/today`));
}

export async function fetchCalendarEvents(days = 7) {
  return readJson(await _apiFetch(`${API_BASE}/productivity/calendar/events?days=${days}`));
}

export async function createCalendarEvent(data) {
  return readJson(await _apiFetch(`${API_BASE}/productivity/calendar/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function ingestManifest(nodeId, manifest) {
  return readJson(await _apiFetch(`${API_BASE}/nodes/${encodeURIComponent(nodeId)}/manifest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(manifest),
  }));
}

// ---------------------------------------------------------------------------

export async function fetchMissionBriefing() {
  return readJson(await _apiFetch(`${API_BASE}/mission/briefing`));
}

export async function fetchDailyFocus() {
  return readJson(await _apiFetch(`${API_BASE}/mission/focus`));
}

export async function fetchProjectHealth() {
  return readJson(await _apiFetch(`${API_BASE}/mission/health`));
}

export async function fetchEveningReview() {
  return readJson(await _apiFetch(`${API_BASE}/mission/evening`));
}

// ---------------------------------------------------------------------------
// Desktop — Phase 11
// ---------------------------------------------------------------------------

export async function fetchLocations() {
  return readJson(await _apiFetch(`${API_BASE}/desktop/locations`));
}

export async function fetchDesktopApps() {
  return readJson(await _apiFetch(`${API_BASE}/desktop/apps`));
}

export async function searchFiles({ query = "", extension = "", location = "" } = {}) {
  const params = new URLSearchParams();
  if (query)     params.set("query", query);
  if (extension) params.set("extension", extension);
  if (location)  params.set("location", location);
  return readJson(await _apiFetch(`${API_BASE}/desktop/files?${params}`));
}

export async function fetchRecentFiles(location = "") {
  const params = new URLSearchParams();
  if (location) params.set("location", location);
  return readJson(await _apiFetch(`${API_BASE}/desktop/recent-files?${params}`));
}

export async function openLocation(name) {
  return readJson(await _apiFetch(`${API_BASE}/desktop/open/location`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }));
}

export async function openApp(name) {
  return readJson(await _apiFetch(`${API_BASE}/desktop/open/app`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }));
}

// ---------------------------------------------------------------------------
// Hardware Operations API (Phase 12A)
// ---------------------------------------------------------------------------

export async function fetchHardwareSummary() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/summary`));
}

export async function fetchHardwareInventory(category = "", search = "") {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (search) params.set("search", search);
  return readJson(await _apiFetch(`${API_BASE}/hardware/inventory?${params}`));
}

export async function createHardwarePart(data) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/inventory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function updateHardwarePart(partId, data) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/inventory/${partId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function deleteHardwarePart(partId) {
  const res = await _apiFetch(`${API_BASE}/hardware/inventory/${partId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(await res.text());
  return { ok: true };
}

export async function fetchHardwareCategories() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/categories`));
}

export async function fetchHardwareProjects(status = "") {
  const params = status ? new URLSearchParams({ status }) : new URLSearchParams();
  return readJson(await _apiFetch(`${API_BASE}/hardware/projects?${params}`));
}

export async function createHardwareProject(data) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function fetchHardwareProject(projectId) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/projects/${projectId}`));
}

export async function updateHardwareProject(projectId, data) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/projects/${projectId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function deleteHardwareProject(projectId) {
  const res = await _apiFetch(`${API_BASE}/hardware/projects/${projectId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(await res.text());
  return { ok: true };
}

export async function assignPartToProject(projectId, partId, quantityRequired = 1) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/projects/${projectId}/parts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ part_id: partId, quantity_required: quantityRequired }),
  }));
}

export async function unassignPartFromProject(projectId, partId) {
  const res = await _apiFetch(`${API_BASE}/hardware/projects/${projectId}/parts/${partId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(await res.text());
  return { ok: true };
}

export async function fetchHardwareOrders(status = "") {
  const params = status ? new URLSearchParams({ status }) : new URLSearchParams();
  return readJson(await _apiFetch(`${API_BASE}/hardware/orders?${params}`));
}

export async function createHardwareOrder(data) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function updateHardwareOrderStatus(orderId, status) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/orders/${orderId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  }));
}

export async function deleteHardwareOrder(orderId) {
  const res = await _apiFetch(`${API_BASE}/hardware/orders/${orderId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(await res.text());
  return { ok: true };
}

// ── Hardware Intelligence (Phase 12B) ─────────────────────────────────────────

export async function fetchHardwareReadiness() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/intelligence/readiness`));
}

export async function fetchHardwareMissingParts() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/intelligence/missing`));
}

export async function fetchHardwareBlocked() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/intelligence/blocked`));
}

export async function fetchHardwareRecommendations() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/intelligence/recommendations`));
}

export async function fetchHardwarePriority() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/intelligence/priority`));
}

// ── Hardware Imports (Phase 12C) ──────────────────────────────────────────────

export async function fetchHardwareImports(limit = 10) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/imports?limit=${limit}`));
}

export async function importHardwareFile(path, sourceType = "auto", project = "") {
  return readJson(await _apiFetch(`${API_BASE}/hardware/imports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, source_type: sourceType, project }),
  }));
}

export async function fetchHardwareImportItems(importId) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/imports/${importId}/items`));
}

export async function fetchProjectInventoryImpact(projectId) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/projects/${projectId}/impact`));
}

export async function sendHardwareAssistantMessage(message, pendingAction = null) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/assistant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, pending_action: pendingAction }),
  }));
}

// ── Hardware Procurement (Phase 12E) ──────────────────────────────────────────

export async function fetchHardwareLowStock() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/intelligence/low-stock`));
}

export async function fetchHardwareAfterDelivery() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/intelligence/after-delivery`));
}

export async function receiveHardwareOrder(orderId) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/orders/${orderId}/receive`, { method: "POST" }));
}

export async function setPartReorderThreshold(partId, threshold) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/inventory/${partId}/threshold`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threshold }),
  }));
}

// ── Hardware Vision (Phase 12F) ────────────────────────────────────────────────

export async function fetchHardwareVisionStatus() {
  return readJson(await _apiFetch(`${API_BASE}/hardware/vision/status`));
}

export async function analyzeHardwareImage(file) {
  const key = getApiKey();
  const form = new FormData();
  form.append("file", file);
  const headers = key ? { "X-API-Key": key } : {};
  return readJson(await fetch(`${API_BASE}/hardware/vision/analyze`, {
    method: "POST",
    headers,
    body: form,
  }));
}

export async function applyVisionDetections(detections) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/vision/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ detections }),
  }));
}

// ---------------------------------------------------------------------------
// Workspace Digital Twin (Phase 15A)
// ---------------------------------------------------------------------------

export async function fetchWorkspaceStatus() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/status`));
}

export async function fetchWorkspaceProjects() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/projects`));
}

export async function fetchWorkspacePriorities() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/priorities`));
}

export async function fetchWorkspaceRecommendations() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/recommendations`));
}

export async function fetchWorkspaceBriefing() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/briefing`));
}

export async function fetchWorkspaceBlocked() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/blocked`));
}

export async function fetchWorkspaceReady() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/ready`));
}

export async function fetchWorkspaceOrderRecommendations() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/order-recommendations`));
}

// ── Screen Awareness (Phase 16A) ────────────────────────────────────────────

export async function fetchWorkspaceContext() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/context`));
}

export async function fetchActiveProject() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/context/project`));
}

export async function fetchActiveFile() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/context/file`));
}

export async function fetchActiveApplication() {
  return readJson(await _apiFetch(`${API_BASE}/workspace/context/application`));
}

export async function fetchRecentSessions(hours = 24, limit = 20) {
  return readJson(await _apiFetch(`${API_BASE}/workspace/context/sessions?hours=${hours}&limit=${limit}`));
}

export async function fetchRecentContextProjects(hours = 24) {
  return readJson(await _apiFetch(`${API_BASE}/workspace/context/recent-projects?hours=${hours}`));
}

// ── Session Continuity (Phase 16B) ──────────────────────────────────────────

export async function fetchWorkspaceSessions(hours = 48, limit = 20) {
  return readJson(await _apiFetch(`${API_BASE}/workspace/sessions?hours=${hours}&limit=${limit}`));
}

export async function fetchWorkspaceAccomplishments(hours = 24) {
  return readJson(await _apiFetch(`${API_BASE}/workspace/recent?hours=${hours}`));
}

export async function fetchContinueProject(project) {
  return readJson(await _apiFetch(`${API_BASE}/workspace/continue/${encodeURIComponent(project)}`));
}

export async function fetchWorkspaceProfile(project) {
  return readJson(await _apiFetch(`${API_BASE}/workspace/profile/${encodeURIComponent(project)}`));
}

export async function restoreWorkspace(project) {
  return readJson(await _apiFetch(`${API_BASE}/workspace/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project }),
  }));
}

// ── Engineering Planner (Phase 15B) ─────────────────────────────────────────

export async function fetchPlannerTemplates() {
  return readJson(await _apiFetch(`${API_BASE}/planner/templates`));
}

export async function fetchPlannerRecommendations() {
  return readJson(await _apiFetch(`${API_BASE}/planner/recommendations`));
}

export async function fetchPlannerWhatCanIBuild() {
  return readJson(await _apiFetch(`${API_BASE}/planner/what-can-i-build`));
}

export async function fetchPlannerBom(project) {
  return readJson(await _apiFetch(`${API_BASE}/planner/bom/${encodeURIComponent(project)}`));
}

export async function fetchPlannerRoadmap(project) {
  return readJson(await _apiFetch(`${API_BASE}/planner/roadmap/${encodeURIComponent(project)}`));
}

export async function fetchPlannerGapAnalysis(project) {
  return readJson(await _apiFetch(`${API_BASE}/planner/gap-analysis/${encodeURIComponent(project)}`));
}

export async function fetchPlannerCanIBuild(project) {
  return readJson(await _apiFetch(`${API_BASE}/planner/can-i-build/${encodeURIComponent(project)}`));
}

export async function fetchPlannerArchitecture(project) {
  return readJson(await _apiFetch(`${API_BASE}/planner/architecture/${encodeURIComponent(project)}`));
}

export async function fetchPlannerProcurement(project) {
  return readJson(await _apiFetch(`${API_BASE}/planner/procurement/${encodeURIComponent(project)}`));
}

export async function createPlannerProject(name, templateId) {
  return readJson(await _apiFetch(`${API_BASE}/planner/project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, template_id: templateId || null }),
  }));
}

export async function designProject(description) {
  return readJson(await _apiFetch(`${API_BASE}/planner/design`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  }));
}

// ── Safety & Approvals (Phase 17A) ──────────────────────────────────────────

export async function fetchApprovals(limit = 50) {
  return readJson(await _apiFetch(`${API_BASE}/approvals?limit=${limit}`));
}

export async function fetchPendingApprovals(sessionId = "") {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return readJson(await _apiFetch(`${API_BASE}/approvals/pending${qs}`));
}

export async function approveAction(code) {
  return readJson(await _apiFetch(`${API_BASE}/approvals/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

export async function rejectAction(code) {
  return readJson(await _apiFetch(`${API_BASE}/approvals/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

export async function fetchSafetyPolicies() {
  return readJson(await _apiFetch(`${API_BASE}/safety/policies`));
}

export async function fetchActivePolicy() {
  return readJson(await _apiFetch(`${API_BASE}/safety/policy`));
}

export async function setSafetyPolicy(profile) {
  return readJson(await _apiFetch(`${API_BASE}/safety/policy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile }),
  }));
}

// ── Workflows (Phase 17B) ──────────────────────────────────────────────────

export async function fetchWorkflows(limit = 50, status = "") {
  const qs = status ? `?limit=${limit}&status=${status}` : `?limit=${limit}`;
  return readJson(await _apiFetch(`${API_BASE}/workflows${qs}`));
}

export async function fetchPendingWorkflows(sessionId = "") {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return readJson(await _apiFetch(`${API_BASE}/workflows/pending${qs}`));
}

export async function fetchWorkflowHistory(limit = 50) {
  return readJson(await _apiFetch(`${API_BASE}/workflows/history?limit=${limit}`));
}

export async function fetchWorkflow(code) {
  return readJson(await _apiFetch(`${API_BASE}/workflows/${encodeURIComponent(code)}`));
}

export async function approveWorkflow(code) {
  return readJson(await _apiFetch(`${API_BASE}/workflows/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

export async function rejectWorkflow(code) {
  return readJson(await _apiFetch(`${API_BASE}/workflows/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

export async function cancelWorkflow(code) {
  return readJson(await _apiFetch(`${API_BASE}/workflows/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

// ── Memory Providers (Phase 18A) ───────────────────────────────────────────

export async function fetchMemoryProviders() {
  return readJson(await _apiFetch(`${API_BASE}/memory/providers`));
}

export async function fetchMemoryHealth() {
  return readJson(await _apiFetch(`${API_BASE}/memory/health`));
}

export async function fetchMemoryTimeline(project = "", limit = 50) {
  const qs = project ? `?project=${encodeURIComponent(project)}&limit=${limit}` : `?limit=${limit}`;
  return readJson(await _apiFetch(`${API_BASE}/memory/timeline${qs}`));
}

export async function fetchMemoryRelationships(entity = "", limit = 20) {
  const qs = entity ? `?entity=${encodeURIComponent(entity)}&limit=${limit}` : `?limit=${limit}`;
  return readJson(await _apiFetch(`${API_BASE}/memory/relationships${qs}`));
}

export async function searchMemory(query, project = "", providers = [], limit = 20) {
  if (!providers.length && limit === 20) {
    const params = new URLSearchParams({ q: query });
    if (project) params.set("project", project);
    return readJson(await _apiFetch(`${API_BASE}/memory/search?${params}`));
  }

  const results = await readJson(await _apiFetch(`${API_BASE}/memory/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, project, providers, limit }),
  }));
  return { ok: true, data: results, count: results.length };
}

// ── Brain63 Steward (Phase 18B) ────────────────────────────────────────────

export async function fetchBrain63Drafts() {
  return readJson(await _apiFetch(`${API_BASE}/brain63/drafts`));
}

export async function fetchBrain63Health() {
  return readJson(await _apiFetch(`${API_BASE}/brain63/health`));
}

export async function fetchBrain63Coverage(project = "") {
  const qs = project ? `?project=${encodeURIComponent(project)}` : "";
  return readJson(await _apiFetch(`${API_BASE}/brain63/coverage${qs}`));
}

export async function createBrain63Draft(type, project, title, detail = "", reason = "") {
  return readJson(await _apiFetch(`${API_BASE}/brain63/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, project, title, detail, reason }),
  }));
}

export async function approveBrain63Draft(code) {
  return readJson(await _apiFetch(`${API_BASE}/brain63/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

export async function rejectBrain63Draft(code) {
  return readJson(await _apiFetch(`${API_BASE}/brain63/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

export async function fetchBrain63Diff(code) {
  return readJson(await _apiFetch(`${API_BASE}/brain63/diff/${encodeURIComponent(code)}`));
}

// ---------------------------------------------------------------------------
// KOSINE — structured memory backend (Phase 19)
// ---------------------------------------------------------------------------

export async function fetchKosineStatus() {
  return readJson(await _apiFetch(`${API_BASE}/kosine/status`));
}

export async function kosineMigratePreview() {
  return readJson(await _apiFetch(`${API_BASE}/kosine/migrate/preview`, { method: "POST" }));
}

export async function kosineMigrate(backup = true) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/migrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backup }),
  }));
}

export async function fetchKosineBackups() {
  return readJson(await _apiFetch(`${API_BASE}/kosine/backups`));
}

export async function kosineRestore(backup_name, confirm = false) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backup_name, confirm }),
  }));
}

export async function fetchKosineAudit(limit = 50) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/audit?limit=${limit}`));
}

export async function kosineMaintenanceScan(limit = 100) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/maintenance/scan?limit=${limit}`));
}

export async function kosineMaintenanceRun(draft = false) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/maintenance/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft }),
  }));
}

export async function fetchKosineSuggestions(limit = 50) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/suggestions?limit=${limit}`));
}

export async function kosineApplySuggestion(code, { approve = false, dry_run = false } = {}) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/suggestions/${encodeURIComponent(code)}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approve, dry_run }),
  }));
}

export async function kosineSubmitSuggestion(code) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/suggestions/${encodeURIComponent(code)}/submit`, { method: "POST" }));
}

export async function kosineApproveSuggestion(code) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/suggestions/${encodeURIComponent(code)}/approve`, { method: "POST" }));
}

export async function kosineRejectSuggestion(code) {
  return readJson(await _apiFetch(`${API_BASE}/kosine/suggestions/${encodeURIComponent(code)}/reject`, { method: "POST" }));
}
