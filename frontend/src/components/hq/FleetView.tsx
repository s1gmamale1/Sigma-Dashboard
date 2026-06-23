import { Activity, Boxes, Network, OctagonAlert } from "lucide-react";
import type { HQHeartbeat, HQOverview, HQSession, HQSwarm, HQWorker } from "../../lib/hq";
import { parseServerDate } from "../../lib/dates";
import { Card } from "../Card";
import { EmptyState } from "../EmptyState";
import { SectionHeader } from "../SectionHeader";
import { StatCard } from "../StatCard";
import { SourceBadge, StalenessBadge } from "./badges";

function WorkerStatusChip({ status }: { status: HQWorker["status"] }) {
  return (
    <span className={`hq-wstatus hq-wstatus--${status}`}>
      <span className="hq-wstatus__dot" aria-hidden="true" />
      {status}
    </span>
  );
}

function shortTime(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(
    parseServerDate(iso)
  );
}

export function FleetView({
  overview,
  workers,
  sessions,
  swarms,
  hbByEntity,
  projectName
}: {
  overview: HQOverview;
  workers: HQWorker[];
  sessions: HQSession[];
  swarms: HQSwarm[];
  hbByEntity: Record<string, HQHeartbeat>;
  projectName: (id: string | null) => string | null;
}) {
  return (
    <section className="view-grid">
      <div className="metric-row">
        <StatCard icon={<Activity aria-hidden="true" />} label="Running" value={overview.workers_running} />
        <StatCard icon={<OctagonAlert aria-hidden="true" />} label="Blocked" value={overview.workers_blocked} />
        <StatCard icon={<Network aria-hidden="true" />} label="Sessions" value={overview.sessions_active} />
        <StatCard icon={<Boxes aria-hidden="true" />} label="Swarms" value={overview.swarms_active} />
      </div>

      <Card wide className="tile">
        <SectionHeader title={`Workers (${workers.length})`} />
        {workers.length ? (
          <div className="hq-table" role="table" aria-label="Workers">
            <div className="hq-row hq-row--head" role="row">
              <span role="columnheader">Worker</span>
              <span role="columnheader">Status</span>
              <span role="columnheader">Project</span>
              <span role="columnheader">Heartbeat</span>
              <span role="columnheader">Source</span>
            </div>
            {workers.map((w) => (
              <div className="hq-row" role="row" key={w.id}>
                <span role="cell">
                  <strong>{w.name}</strong>
                  <span className="muted"> {w.model ?? w.kind}</span>
                </span>
                <span role="cell"><WorkerStatusChip status={w.status} /></span>
                <span role="cell" className="muted">{projectName(w.project_id) ?? "—"}</span>
                <span role="cell"><StalenessBadge seconds={hbByEntity[w.id]?.staleness_seconds ?? null} /></span>
                <span role="cell"><SourceBadge source={w.source} /></span>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No workers reported" />
        )}
      </Card>

      <Card className="tile">
        <SectionHeader title={`Sessions (${sessions.length})`} />
        {sessions.length ? (
          <div className="hq-list">
            {sessions.map((s) => (
              <div className="hq-listrow" key={s.id}>
                <div className="hq-listrow__main">
                  <strong>{s.status ?? "session"}</strong>
                  <span className="muted">last activity {shortTime(s.last_activity)}</span>
                </div>
                <SourceBadge source={s.source} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No active sessions" />
        )}
      </Card>

      <Card className="tile">
        <SectionHeader title={`Swarms (${swarms.length})`} />
        {swarms.length ? (
          <div className="hq-list">
            {swarms.map((sw) => (
              <div className="hq-listrow" key={sw.id}>
                <div className="hq-listrow__main">
                  <strong>{sw.name}</strong>
                  <span className="muted">
                    {sw.topology ?? "swarm"} · {sw.member_worker_ids.length} members
                  </span>
                </div>
                <SourceBadge source={sw.source} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No swarms reported" />
        )}
      </Card>
    </section>
  );
}
