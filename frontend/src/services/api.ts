import type {
  EmergencyAdvisory,
  LiveWeatherSummary,
  RainInput,
  ReplayEvent,
  ReplayState,
  SpotRisk,
} from "../types";

export async function fetchRisk(rain: RainInput): Promise<SpotRisk[]> {
  const params = new URLSearchParams({
    rain_1h_mm: String(rain.rain_1h_mm),
    rain_3h_mm: String(rain.rain_3h_mm),
    forecast_2h_mm: String(rain.forecast_2h_mm),
  });
  const res = await fetch(`/api/risk?${params}`);
  if (!res.ok) throw new Error(`Risk API returned ${res.status}`);
  return res.json();
}

export async function fetchLiveWeather(force = false): Promise<LiveWeatherSummary> {
  const res = await fetch(`/api/weather/live${force ? "?force=true" : ""}`);
  if (!res.ok) throw new Error(`Weather API returned ${res.status}`);
  return res.json();
}

export async function fetchLiveRisk(): Promise<SpotRisk[]> {
  const res = await fetch("/api/weather/risk");
  if (!res.ok) throw new Error(`Live Risk API returned ${res.status}`);
  return res.json();
}

export async function fetchAgentAdvisory(
  spots: SpotRisk[],
  scenarioName?: string
): Promise<EmergencyAdvisory> {
  const url = scenarioName
    ? `/api/agent/advisory?scenario_name=${encodeURIComponent(scenarioName)}`
    : "/api/agent/advisory";
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spots),
  });
  if (!res.ok) throw new Error(`Agent Advisory API returned ${res.status}`);
  return res.json();
}

export async function fetchLiveAgentAdvisory(): Promise<EmergencyAdvisory> {
  const res = await fetch("/api/agent/advisory/live");
  if (!res.ok) throw new Error(`Live Agent Advisory API returned ${res.status}`);
  return res.json();
}

export async function fetchReplayEvents(): Promise<ReplayEvent[]> {
  const res = await fetch("/api/replay/events");
  if (!res.ok) throw new Error(`Failed to load replay events (${res.status})`);
  return res.json();
}

export async function startReplay(eventId: string): Promise<ReplayState> {
  const res = await fetch(`/api/replay/start/${eventId}`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to start replay (${res.status})`);
  return res.json();
}

export async function getReplayState(runId: string): Promise<ReplayState> {
  const res = await fetch(`/api/replay/${runId}/state`);
  if (!res.ok) throw new Error(`Failed to get replay state (${res.status})`);
  return res.json();
}

export async function nextReplayStep(runId: string): Promise<ReplayState> {
  const res = await fetch(`/api/replay/${runId}/next`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to advance replay step (${res.status})`);
  return res.json();
}

export async function pauseReplay(runId: string): Promise<ReplayState> {
  const res = await fetch(`/api/replay/${runId}/pause`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to pause replay (${res.status})`);
  return res.json();
}

export async function resumeReplay(runId: string): Promise<ReplayState> {
  const res = await fetch(`/api/replay/${runId}/resume`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to resume replay (${res.status})`);
  return res.json();
}

export async function resetReplay(runId: string): Promise<ReplayState> {
  const res = await fetch(`/api/replay/${runId}/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to reset replay (${res.status})`);
  return res.json();
}
