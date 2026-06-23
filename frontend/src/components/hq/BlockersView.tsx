import type { HQBlocker, HQHeartbeat, Severity } from "../../lib/hq";
import { Card } from "../Card";
import { EmptyState } from "../EmptyState";
import { SectionHeader } from "../SectionHeader";
import { SourceBadge, StalenessBadge } from "./badges";
import { stalenessLevel } from "./staleness";

const SEVERITY_RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const LEVEL_RANK: Record<string, number> = { dead: 0, unknown: 1, stale: 2, live: 3 };

export function BlockersView({
  blockers,
  heartbeats
}: {
  blockers: HQBlocker[];
  heartbeats: HQHeartbeat[];
}) {
  const sortedBlockers = [...blockers].sort(
    (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]
  );
  const unhealthy = heartbeats
    .filter((h) => stalenessLevel(h.staleness_seconds) !== "live")
    .sort(
      (a, b) =>
        LEVEL_RANK[stalenessLevel(a.staleness_seconds)] -
        LEVEL_RANK[stalenessLevel(b.staleness_seconds)]
    );

  return (
    <section className="view-grid">
      <Card wide className="tile">
        <SectionHeader title={`Blockers (${blockers.length})`} />
        {sortedBlockers.length ? (
          <div className="hq-list">
            {sortedBlockers.map((b) => (
              <div className="hq-listrow" key={b.id}>
                <span className={`hq-sev hq-sev--${b.severity}`}>{b.severity}</span>
                <div className="hq-listrow__main">
                  <strong>{b.title}</strong>
                  <span className="muted">
                    {b.entity_type ?? "—"}
                    {b.owner ? ` · @${b.owner}` : ""} · {b.status}
                  </span>
                </div>
                <SourceBadge source={b.source} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No open blockers" />
        )}
      </Card>

      <Card className="tile">
        <SectionHeader title={`Heartbeat health (${unhealthy.length} need attention)`} />
        {unhealthy.length ? (
          <div className="hq-list">
            {unhealthy.map((h) => (
              <div className="hq-listrow" key={`${h.entity_type}:${h.entity_id}`}>
                <div className="hq-listrow__main">
                  <strong>{h.entity_type}</strong>
                  <span className="muted">{h.entity_id}</span>
                </div>
                <StalenessBadge seconds={h.staleness_seconds} />
                <SourceBadge source={h.source} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="All heartbeats healthy" />
        )}
      </Card>
    </section>
  );
}
