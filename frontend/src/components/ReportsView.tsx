import type { PerformanceRow, Report } from "../lib/types";
import { BarChart } from "./BarChart";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { SectionHeader } from "./SectionHeader";
import { StatusPill } from "./StatusPill";

function RatingDots({ rating }: { rating: number | null }) {
  const label = rating ? `${rating} of 4` : "no rating";
  if (rating == null) {
    return (
      <span className="rating-dots" aria-label={label}>
        —
      </span>
    );
  }
  const filled = Math.max(0, Math.min(4, rating));
  return (
    <span className="rating-dots" aria-label={label}>
      {Array.from({ length: 4 }, (_, i) => (
        <span key={i} className={i < filled ? "dot is-on" : "dot"} aria-hidden="true" />
      ))}
    </span>
  );
}

export function ReportsView({ reports, performance }: { reports: Report[]; performance: PerformanceRow[] }) {
  return (
    <section className="view-grid">
      <Card wide>
        <SectionHeader title="Daily reports" />
        {reports.length ? (
          <div className="report-grid">
            {reports.map((report) => (
              <article className="report-card" key={report.id}>
                <div>
                  <strong>{report.person.display_name}</strong>
                  <span className="muted">{report.source_topic ?? "No topic"}</span>
                </div>
                <p>{report.summary}</p>
                {report.extras ? <small className="muted">{report.extras}</small> : null}
                <footer className="report-card__foot">
                  <RatingDots rating={report.rating} />
                  {report.missing ? <StatusPill value="missing" /> : <span className="muted">Submitted</span>}
                </footer>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No reports for this date" />
        )}
      </Card>

      <Card>
        <SectionHeader title="Performance rank" />
        {performance.length ? (
          <div className="stack">
            {performance.map((row, index) => (
              <div className="rank-row" key={row.person.id}>
                <span className="rank-badge">{index + 1}</span>
                <strong>{row.person.display_name}</strong>
                <span className="muted">
                  {row.average_rating ?? "—"} avg · {row.report_completion_rate}% complete
                </span>
                <b>{row.missing_days} missing</b>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No performance data" />
        )}
      </Card>

      <Card>
        <SectionHeader title="Rating average" />
        <BarChart
          data={performance.map((r) => ({ label: r.person.display_name, value: r.average_rating ?? 0 }))}
          ariaLabel="Average rating per person, out of 4"
          max={4}
        />
      </Card>
    </section>
  );
}
