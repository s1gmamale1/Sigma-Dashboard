import type { Report } from "../lib/types";
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

export function ReportsView({ reports }: { reports: Report[] }) {
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
    </section>
  );
}
