import { useMemo, useState } from "react";
import { ArrowDownUp, ChevronDown } from "lucide-react";
import type { CompositeGrade, Evaluation, Feedback, PerformanceRow } from "../lib/types";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { SectionHeader } from "./SectionHeader";
import { SegmentedControl } from "./SegmentedControl";
import { Sparkline } from "./Sparkline";

export type PeriodKind = "week" | "month" | "custom";

export interface PerformancePeriod {
  kind: PeriodKind;
  from: string;
  to: string;
}

interface PerformanceViewProps {
  token: string;
  performance: PerformanceRow[];
  evaluations: Evaluation[];
  feedback: Feedback[];
  period: PerformancePeriod;
  onPeriod: (period: PerformancePeriod) => void;
}

const GRADE_PILL_CLASS: Record<CompositeGrade, string> = {
  Over: "pill-over",
  Good: "pill-good",
  Average: "pill-average",
  Under: "pill-under"
};

const HOURS_BASELINE = 9;

function GradePill({ grade }: { grade: CompositeGrade }) {
  return (
    <span className={`pill perf-grade ${GRADE_PILL_CLASS[grade]}`}>
      <span className="pill__dot" aria-hidden="true" />
      {grade}
    </span>
  );
}

function pct(value: number): string {
  return `${Math.round(value)}%`;
}

function ratingLabel(value: number | null): string {
  return value == null ? "—" : pct(value);
}

function timeLabel(value: string | null): string {
  return value ?? "—";
}

function firstLine(text: string | null | undefined): string {
  if (!text) return "—";
  const trimmed = text.trim();
  const idx = trimmed.indexOf("\n");
  return idx === -1 ? trimmed : trimmed.slice(0, idx);
}

function feedbackDate(value: string): string {
  // Date-only field (YYYY-MM-DD): parse at local noon so it never crosses a day boundary in any tz.
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(`${value}T12:00:00`)
  );
}

function latestEvaluationFor(evaluations: Evaluation[], personId: number): Evaluation | null {
  let best: Evaluation | null = null;
  for (const ev of evaluations) {
    if (ev.person.id !== personId) continue;
    if (!best || ev.period_start > best.period_start || (ev.period_start === best.period_start && ev.id > best.id)) {
      best = ev;
    }
  }
  return best;
}

function EvaluationVerdict({ evaluation }: { evaluation: Evaluation }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="perf-verdict">
      <div className="perf-verdict__head">
        <span className="perf-verdict__grade">{evaluation.grade}</span>
        <button
          type="button"
          className="perf-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Show distilled" : "Show full narrative"}
          <ChevronDown size={14} aria-hidden="true" className={expanded ? "perf-chevron is-open" : "perf-chevron"} />
        </button>
      </div>
      <dl className="perf-verdict__lines">
        <div>
          <dt>What</dt>
          <dd>{expanded ? evaluation.what : firstLine(evaluation.what)}</dd>
        </div>
        <div>
          <dt>How</dt>
          <dd>{expanded ? evaluation.how : firstLine(evaluation.how)}</dd>
        </div>
        <div>
          <dt>Why</dt>
          <dd>{expanded ? evaluation.why : firstLine(evaluation.why)}</dd>
        </div>
      </dl>
    </div>
  );
}

function PerformanceDetail({
  row,
  evaluation,
  feedback
}: {
  row: PerformanceRow;
  evaluation: Evaluation | null;
  feedback: Feedback[];
}) {
  const hoursLabel = row.avg_hours == null ? "—" : `${row.avg_hours.toFixed(1)}h`;
  return (
    <div className="perf-detail">
      <section className="perf-col" aria-label="What — output">
        <h3 className="perf-col__title">What</h3>
        <div className="perf-col__rating">
          <strong className="num">{ratingLabel(row.average_rating)}</strong>
          <span className="muted"> avg</span>
          <Sparkline data={row.rating_trend} ariaLabel={`Rating trend for ${row.person.display_name}`} />
        </div>
        <p className="perf-accomplishment">{row.top_accomplishment ?? "No standout accomplishment logged."}</p>
        <p className="perf-col__meta muted num">
          {pct(row.report_completion_rate)} reports complete · {row.missing_days} missing
        </p>
      </section>

      <section className="perf-col" aria-label="How — work pattern">
        <h3 className="perf-col__title">How</h3>
        <p className="perf-col__meta num">
          In {timeLabel(row.avg_check_in)} · Out {timeLabel(row.avg_check_out)}
        </p>
        <ul className="perf-counts">
          <li><span className="muted">On time</span><b className="num">{row.on_time_count}</b></li>
          <li><span className="muted">Late</span><b className="num">{row.late_count}</b></li>
          <li><span className="muted">15+</span><b className="num">{row.late15_count}</b></li>
          <li><span className="muted">No Show</span><b className="num">{row.no_show_count}</b></li>
          <li><span className="muted">Absent</span><b className="num">{row.absent_count}</b></li>
        </ul>
        <p className="perf-col__meta muted num">
          {pct(row.punctuality_rate)} punctual · {hoursLabel} vs ~{HOURS_BASELINE}h
        </p>
        {row.compensates ? (
          <p className="perf-compensates">Came late but stayed late to compensate.</p>
        ) : null}
      </section>

      <section className="perf-col" aria-label="Why — verdict">
        <h3 className="perf-col__title">Why</h3>
        {evaluation ? (
          <EvaluationVerdict evaluation={evaluation} />
        ) : (
          <p className="muted">No evaluation recorded for this period.</p>
        )}
        {feedback.length ? (
          <ul className="perf-feedback">
            {feedback.map((item) => (
              <li className="perf-feedback__item" key={item.id}>
                <p className="perf-feedback__note">{item.note}</p>
                <p className="perf-feedback__meta muted num">
                  {feedbackDate(item.feedback_date)}
                  {item.source ? ` · ${item.source}` : ""}
                  {item.grade_adjustment ? ` · ${item.grade_adjustment > 0 ? "+" : ""}${item.grade_adjustment} band` : ""}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No feedback in this period.</p>
        )}
      </section>
    </div>
  );
}

function LeaderboardRow({
  row,
  rank,
  expanded,
  onToggle,
  evaluation,
  feedback
}: {
  row: PerformanceRow;
  rank: number;
  expanded: boolean;
  onToggle: () => void;
  evaluation: Evaluation | null;
  feedback: Feedback[];
}) {
  const panelId = `perf-panel-${row.person.id}`;
  return (
    <div className={`perf-row${expanded ? " is-open" : ""}`}>
      <button
        type="button"
        className="perf-row__head"
        aria-expanded={expanded}
        aria-controls={panelId}
        aria-label={`Rank ${rank}, ${row.person.display_name}, grade ${row.composite_grade}`}
        onClick={onToggle}
      >
        <span
          className={`perf-rank num${rank <= 3 ? ` perf-rank--medal perf-rank--medal-${rank}` : ""}`}
          aria-hidden="true"
        >
          {rank}
        </span>
        <GradePill grade={row.composite_grade} />
        <span className="perf-name">{row.person.display_name}</span>
        <span className="perf-rating">
          <span className="num">{ratingLabel(row.average_rating)}</span>
          <Sparkline data={row.rating_trend} ariaLabel={`Rating trend for ${row.person.display_name}`} />
        </span>
        <span className="perf-stat num" title="Report completion">{pct(row.report_completion_rate)}</span>
        <span className="perf-stat num" title="Punctuality">{pct(row.punctuality_rate)}</span>
        <span className="perf-accomplishment-line">{row.top_accomplishment ?? "—"}</span>
        <ChevronDown size={18} aria-hidden="true" className={expanded ? "perf-chevron is-open" : "perf-chevron"} />
      </button>
      {expanded ? (
        <div className="perf-row__panel" id={panelId} role="region" aria-label={`${row.person.display_name} — performance detail`}>
          <PerformanceDetail row={row} evaluation={evaluation} feedback={feedback} />
        </div>
      ) : null}
    </div>
  );
}

export function PerformanceView({
  performance,
  evaluations,
  feedback,
  period,
  onPeriod
}: PerformanceViewProps) {
  const [openId, setOpenId] = useState<number | null>(null);
  const [worstFirst, setWorstFirst] = useState(false);

  const feedbackByPerson = useMemo(() => {
    const map = new Map<number, Feedback[]>();
    for (const item of feedback) {
      const list = map.get(item.person.id);
      if (list) list.push(item);
      else map.set(item.person.id, [item]);
    }
    return map;
  }, [feedback]);

  // Pin each person's canonical best→worst rank, then display in either order. The rank stays
  // tied to leaderboard position regardless of the sort toggle.
  const ranked = useMemo(() => performance.map((row, i) => ({ row, rank: i + 1 })), [performance]);
  const ordered = useMemo(
    () => (worstFirst ? [...ranked].reverse() : ranked),
    [ranked, worstFirst]
  );

  const periodItems = [
    { id: "week", label: "Week" },
    { id: "month", label: "Month" },
    { id: "custom", label: "Custom" }
  ];

  return (
    <section className="view-grid">
      <Card wide className="perf-card">
        <SectionHeader
          title="Performance leaderboard"
          eyebrow="What · How · Why"
          actions={
            <div className="perf-controls">
              <SegmentedControl
                items={periodItems}
                value={period.kind}
                onChange={(id) => onPeriod({ ...period, kind: id as PeriodKind })}
                ariaLabel="Performance period"
              />
              <button
                type="button"
                className={`perf-sort${worstFirst ? " is-active" : ""}`}
                aria-pressed={worstFirst}
                onClick={() => setWorstFirst((v) => !v)}
              >
                <ArrowDownUp size={16} aria-hidden="true" />
                {worstFirst ? "Worst first" : "Best first"}
              </button>
            </div>
          }
        />

        {period.kind === "custom" ? (
          <div className="perf-range">
            <label className="perf-range__field">
              <span className="muted">From</span>
              <input
                type="date"
                value={period.from}
                max={period.to}
                aria-label="Performance range start"
                onChange={(e) =>
                  onPeriod({ ...period, from: e.target.value > period.to ? period.to : e.target.value })
                }
              />
            </label>
            <label className="perf-range__field">
              <span className="muted">To</span>
              <input
                type="date"
                value={period.to}
                min={period.from}
                aria-label="Performance range end"
                onChange={(e) =>
                  onPeriod({ ...period, to: e.target.value < period.from ? period.from : e.target.value })
                }
              />
            </label>
          </div>
        ) : null}

        {ordered.length ? (
          <div className="perf-list">
            <div className="perf-list__head" aria-hidden="true">
              <span>#</span>
              <span>Grade</span>
              <span>Name</span>
              <span>Rating</span>
              <span>Reports</span>
              <span>Punctual</span>
              <span>Highlight</span>
              <span />
            </div>
            {ordered.map(({ row, rank }) => (
              <LeaderboardRow
                key={row.person.id}
                row={row}
                rank={rank}
                expanded={openId === row.person.id}
                onToggle={() => setOpenId((id) => (id === row.person.id ? null : row.person.id))}
                evaluation={latestEvaluationFor(evaluations, row.person.id)}
                feedback={feedbackByPerson.get(row.person.id) ?? []}
              />
            ))}
          </div>
        ) : (
          <EmptyState title="No performance data for this period" />
        )}
      </Card>
    </section>
  );
}
