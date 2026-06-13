import type { Report } from "../lib/types";
import { shortDate } from "../lib/dates";
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

export function ReportsView({
  reports,
  requestedDate,
  fallbackDate
}: {
  reports: Report[];
  /** The globally selected date the user asked for. */
  requestedDate?: string;
  /** The earlier date actually being shown when it differs from requestedDate; otherwise null. */
  fallbackDate?: string | null;
}) {
  const showBanner = !!fallbackDate && !!requestedDate && fallbackDate !== requestedDate;
  return (
    <section className="view-grid">
      <Card wide>
        <SectionHeader title="Daily reports" />
        {showBanner ? (
          <p className="reports-fallback-banner" role="status">
            No reports filed for {shortDate(requestedDate!)} yet — showing {shortDate(fallbackDate!)}.
          </p>
        ) : null}
        {reports.length ? (
          <div className="report-grid">
            {reports.map((report) => (
              <article className="report-card" key={report.id}>
                <div>
                  <strong>{report.person.display_name}</strong>
                </div>
                <p>{report.summary}</p>
                {report.extras ? <small className="muted">{report.extras}</small> : null}
                <footer className="report-card__foot">
                  <RatingScore rating={report.rating} />
                  {report.missing ? <StatusPill value="missing" /> : null}
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
