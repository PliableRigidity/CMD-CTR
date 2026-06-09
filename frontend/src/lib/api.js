const API_BASE = "http://127.0.0.1:8001/api";
const WS_BASE = "ws://127.0.0.1:8001/api/ws/events";
export const WS_WAKE_URL = "ws://127.0.0.1:8001/api/ws/wake";

async function readJson(response) {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Request failed.");
  }
  return response.json();
}

export async function fetchMode() {
  return readJson(await fetch(`${API_BASE}/mode`));
}

export async function setMode(mode) {
  return readJson(
    await fetch(`${API_BASE}/mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),
  );
}

export async function sendChat(payload) {
  return readJson(
    await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function sendDecision(payload) {
  return readJson(
    await fetch(`${API_BASE}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchActions() {
  return readJson(await fetch(`${API_BASE}/actions`));
}

export async function fetchMissions() {
  return readJson(await fetch(`${API_BASE}/missions`));
}

export async function executeActionAlias(target) {
  return readJson(
    await fetch(`${API_BASE}/actions/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    }),
  );
}

export async function openAppAction(actionId, args = []) {
  return readJson(
    await fetch(`${API_BASE}/actions/open-app`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: actionId, args }),
    }),
  );
}

export async function openUrlAction(target) {
  return readJson(
    await fetch(`${API_BASE}/actions/open-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    }),
  );
}

export async function fetchDevices() {
  return readJson(await fetch(`${API_BASE}/devices`));
}

export async function fetchWorldEvents({ live = true, category, country } = {}) {
  const query = new URLSearchParams();
  if (live) query.set("live", "true");
  if (category) query.set("category", category);
  if (country) query.set("country", country);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return readJson(await fetch(`${API_BASE}/world/events${suffix}`));
}

export async function fetchVoiceStatus() {
  return readJson(await fetch(`${API_BASE}/voice/status`));
}

export async function updateVoiceState(payload) {
  return readJson(
    await fetch(`${API_BASE}/voice/state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchRoute(payload) {
  return readJson(
    await fetch(`${API_BASE}/maps/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchLogs() {
  return readJson(await fetch(`${API_BASE}/events/logs`));
}

export async function fetchAudioState() {
  return readJson(await fetch(`${API_BASE}/system/audio`));
}

async function postSystem(path, body) {
  return readJson(
    await fetch(`${API_BASE}${path}`, {
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
  return new WebSocket(WS_BASE);
}

// ---------------------------------------------------------------------------
// Memory API
// ---------------------------------------------------------------------------

export async function fetchHistory(sessionId = "default-session", limit = 100) {
  return readJson(
    await fetch(`${API_BASE}/memory/history?session_id=${encodeURIComponent(sessionId)}&limit=${limit}`)
  );
}

export async function clearHistory(sessionId = "default-session") {
  return readJson(
    await fetch(`${API_BASE}/memory/history?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    })
  );
}

export async function fetchFacts() {
  return readJson(await fetch(`${API_BASE}/memory/facts`));
}

export async function saveFact(key, value) {
  return readJson(
    await fetch(`${API_BASE}/memory/facts?key=${encodeURIComponent(key)}&value=${encodeURIComponent(value)}`, {
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
  const response = await fetch(`${API_BASE}/voice/transcribe`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function fetchVoiceDiagnostics() {
  return readJson(await fetch(`${API_BASE}/voice/diagnostics`));
}

export async function synthesizeSpeech(text) {
  const response = await fetch(`${API_BASE}/voice/synthesize`, {
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
  return readJson(await fetch(`${API_BASE}/nodes`));
}

export async function createNode(data) {
  return readJson(
    await fetch(`${API_BASE}/nodes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function deleteNode(id) {
  const res = await fetch(`${API_BASE}/nodes/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function updateNode(id, data) {
  return readJson(
    await fetch(`${API_BASE}/nodes/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function updateNodeMetrics(id, metrics) {
  return readJson(
    await fetch(`${API_BASE}/nodes/${id}/metrics`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metrics),
    }),
  );
}

export async function probeNode(id) {
  return readJson(
    await fetch(`${API_BASE}/nodes/${id}/probe`, {
      method: "POST",
    }),
  );
}

// ---------------------------------------------------------------------------
// Watch Officer
// ---------------------------------------------------------------------------

export async function fetchWatchAlerts() {
  return readJson(await fetch(`${API_BASE}/watch`));
}

export async function createWatchAlert(data) {
  return readJson(
    await fetch(`${API_BASE}/watch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  );
}

export async function dismissWatchAlert(id) {
  return readJson(
    await fetch(`${API_BASE}/watch/${id}/dismiss`, { method: "POST" }),
  );
}
