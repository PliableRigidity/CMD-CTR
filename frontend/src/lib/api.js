const API_BASE = "http://127.0.0.1:8000/api";
const WS_BASE = "ws://127.0.0.1:8000/api/ws/events";

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
