// Pure heartbeat-staleness helpers (no React) so the load-bearing logic is unit-tested.
// Thresholds are UI-side display bands; the backend's own healthy flag uses its own
// stale window (default 120s) — these bands add an amber "stale" tier for the UI.

export type StalenessLevel = "live" | "stale" | "dead" | "unknown";

const LIVE_MAX = 120; // <= 2 min: green
const STALE_MAX = 600; // <= 10 min: amber; beyond: red

export function stalenessLevel(seconds: number | null): StalenessLevel {
  if (seconds === null || seconds === undefined) return "unknown";
  if (seconds <= LIVE_MAX) return "live";
  if (seconds <= STALE_MAX) return "stale";
  return "dead";
}

export function formatStaleness(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
