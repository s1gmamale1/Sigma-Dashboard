import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PerformanceRow, Report } from "../lib/types";
import { EmptyState } from "./EmptyState";

export function ReportsView({ reports, performance }: { reports: Report[]; performance: PerformanceRow[] }) {
  const chartData = performance.map((row) => ({
    name: row.person.display_name,
    rating: row.average_rating ?? 0,
    completion: row.report_completion_rate
  }));

  return (
    <section className="view-grid">
      <section className="panel wide">
        <header className="panel-header">
          <h2>Daily reports</h2>
        </header>
        {reports.length ? (
          <div className="report-grid">
            {reports.map((report) => (
              <article className="report-card" key={report.id}>
                <div>
                  <strong>{report.person.display_name}</strong>
                  <span>{report.source_topic ?? "No topic"}</span>
                </div>
                <p>{report.summary}</p>
                {report.extras ? <small>{report.extras}</small> : null}
                <footer>
                  <b>{report.rating ? `${report.rating}/4` : "—"}</b>
                  <span>{report.missing ? "Missing" : "Submitted"}</span>
                </footer>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No reports for this date" />
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2>Performance rank</h2>
        </header>
        {performance.length ? (
          <div className="stack">
            {performance.map((row, index) => (
              <article className="list-item" key={row.person.id}>
                <strong>{index + 1}. {row.person.display_name}</strong>
                <span>{row.average_rating ?? "—"} avg · {row.report_completion_rate}% complete</span>
                <b>{row.missing_days} missing</b>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No performance data" />
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2>Rating average</h2>
        </header>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData}>
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, 4]} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="rating" fill="var(--accent)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>
    </section>
  );
}

