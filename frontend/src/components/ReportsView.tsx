import type { Report } from "../lib/types";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { SectionHeader } from "./SectionHeader";
import { StatusPill } from "./StatusPill";

function scoreBand(score: number): string {
  if (score >= 85) return "over";
  if (score >= 70) return "good";
  if (score >= 50) return "average";
  return "under";
}

function RatingScore({ rating }: { rating: number | null }) {
  if (rating == null) {
    return (
      <span className="rating-score num" aria-label="no score">
        —
      </span>
    );
  }
  const score = Math.max(0, Math.min(100, rating));
  return (
    <span className={`rating-score num rating-score--${scoreBand(score)}`} aria-label={`score ${score} of 100`}>
      {score}%
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
                  <RatingScore rating={report.rating} />
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
