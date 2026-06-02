import type React from "react";
import { AlertTriangle, CalendarCheck, FileWarning, Target } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Overview } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { StatusPill } from "./StatusPill";
import { shortTime } from "../lib/dates";

export function OverviewView({ overview }: { overview: Overview }) {
  const chargeData = overview.weekly_summary.map((row) => ({
    name: row.person.display_name,
    charge: row.total_charge_uzs,
    lates: row.lates
  }));

  return (
    <section className="view-grid">
      <div className="metric-row">
        <Metric icon={<CalendarCheck />} label="Shift records" value={overview.today_attendance.length} />
        <Metric icon={<FileWarning />} label="Missing reports" value={overview.missing_reports_count} />
        <Metric icon={<Target />} label="At-risk goals" value={overview.at_risk_goals.length} />
        <Metric icon={<AlertTriangle />} label="Stale topics" value={overview.stale_project_topics.length} />
      </div>

      <section className="panel wide">
        <header className="panel-header">
          <h2>Tonight</h2>
        </header>
        {overview.today_attendance.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Status</th>
                  <th>In</th>
                  <th>Out</th>
                  <th>Chase</th>
                </tr>
              </thead>
              <tbody>
                {overview.today_attendance.map((record) => (
                  <tr key={record.id}>
                    <td>{record.person.display_name}</td>
                    <td><StatusPill value={record.status} /></td>
                    <td>{shortTime(record.check_in_at)}</td>
                    <td>{shortTime(record.check_out_at)}</td>
                    <td><StatusPill value={record.chase_state} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No shift data yet" />
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2>Weekly charge load</h2>
        </header>
        {chargeData.length ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chargeData}>
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="charge" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState title="No weekly summary yet" />
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2>Goal risk</h2>
        </header>
        {overview.at_risk_goals.length ? (
          <div className="stack">
            {overview.at_risk_goals.map((goal) => (
              <article className="list-item" key={goal.id}>
                <strong>{goal.title}</strong>
                <span>{goal.deadline ?? "No deadline"}</span>
                <div className="progress"><span style={{ width: `${goal.progress_percent}%` }} /></div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No active goal risk" />
        )}
      </section>
    </section>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="metric">
      <span className="metric-icon" aria-hidden="true">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
