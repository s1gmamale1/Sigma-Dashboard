import { AlertTriangle, CalendarCheck, FileWarning, Target } from "lucide-react";
import type { Overview } from "../lib/types";
import { shortTime } from "../lib/dates";
import { Avatar } from "./Avatar";
import { BarChart } from "./BarChart";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { SectionHeader } from "./SectionHeader";
import { StatCard } from "./StatCard";
import { StatusPill } from "./StatusPill";

export function OverviewView({ overview }: { overview: Overview }) {
  return (
    <section className="view-grid">
      <div className="metric-row">
        <StatCard
          icon={<CalendarCheck aria-hidden="true" />}
          label="Shift records"
          value={overview.today_attendance.length}
        />
        <StatCard
          icon={<FileWarning aria-hidden="true" />}
          label="Missing reports"
          value={overview.missing_reports_count}
        />
        <StatCard
          icon={<Target aria-hidden="true" />}
          label="At-risk goals"
          value={overview.at_risk_goals.length}
        />
        <StatCard
          icon={<AlertTriangle aria-hidden="true" />}
          label="Stale topics"
          value={overview.stale_project_topics.length}
        />
      </div>

      <Card wide className="tile">
        <SectionHeader title="Tonight" />
        {overview.today_attendance.length ? (
          <div className="roster">
            {overview.today_attendance.map((record) => (
              <div className="roster-row" key={record.id}>
                <Avatar name={record.person.display_name} />
                <div className="roster-row__main">
                  <strong>{record.person.display_name}</strong>
                  <span className="muted">
                    in {shortTime(record.check_in_at)} · out {shortTime(record.check_out_at)}
                  </span>
                </div>
                <div className="roster-row__status">
                  <StatusPill value={record.status} />
                  <StatusPill value={record.chase_state} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No shift data yet" />
        )}
      </Card>

      <Card className="tile">
        <SectionHeader title="Weekly lateness" />
        {overview.weekly_summary.length ? (
          <BarChart
            data={overview.weekly_summary.map((row) => ({
              label: row.person.display_name,
              value: row.late,
              value2: row.late_15
            }))}
            ariaLabel="Weekly late and 15+ late counts per person"
            seriesLabels={["Late", "15+ Late"]}
          />
        ) : (
          <EmptyState title="No weekly summary yet" />
        )}
      </Card>

      <Card className="tile">
        <SectionHeader title="Goal risk" />
        {overview.at_risk_goals.length ? (
          <div className="risk">
            {overview.at_risk_goals.map((goal) => (
              <div className="risk-row" key={goal.id}>
                <div className="risk-row__head">
                  <strong>{goal.title}</strong>
                  <span className="muted">{goal.deadline ?? "No deadline"}</span>
                </div>
                <div className="progress">
                  <span style={{ width: `${goal.progress_percent}%` }} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No active goal risk" />
        )}
      </Card>
    </section>
  );
}
