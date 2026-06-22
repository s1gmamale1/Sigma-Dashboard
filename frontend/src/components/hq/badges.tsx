// Small presentational badges for the HQ tab: source labels (with a loud MOCK
// pill so mocked/unverified data is never mistaken for live state) and heartbeat
// staleness chips.
import { formatStaleness, stalenessLevel } from "./staleness";

/** A source label. The mock source gets a deliberately loud badge. */
export function SourceBadge({ source }: { source: string }) {
  const isMock = source === "mock";
  return (
    <span className={`hq-source hq-source--${source}${isMock ? " hq-source--mock" : ""}`} title={`source: ${source}`}>
      {isMock ? "MOCK" : source}
    </span>
  );
}

/** Health of a single upstream source, derived from meta.sources. */
export function SourceHealth({ name, healthy }: { name: string; healthy: boolean }) {
  return (
    <span className={`hq-srchealth ${healthy ? "is-up" : "is-down"}`} title={healthy ? "healthy" : "unreachable / unconfigured"}>
      <span className="hq-srchealth__dot" aria-hidden="true" />
      {name}
    </span>
  );
}

/** Heartbeat freshness chip — green live / amber stale / red dead / grey unknown. */
export function StalenessBadge({ seconds }: { seconds: number | null }) {
  const level = stalenessLevel(seconds);
  return (
    <span className={`hq-stale hq-stale--${level}`} title={`heartbeat: ${formatStaleness(seconds)}`}>
      <span className="hq-stale__dot" aria-hidden="true" />
      {level === "unknown" ? "no beat" : formatStaleness(seconds)}
    </span>
  );
}
