import type { Goal } from "../lib/types";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { SectionHeader } from "./SectionHeader";
import { StatusPill } from "./StatusPill";

export function GoalsView({ goals }: { goals: Goal[] }) {
  return (
    <section className="view-grid">
      <Card wide>
        <SectionHeader title="Active goals" />
        {goals.length ? (
          <div className="goal-grid">
            {goals.map((goal) => (
              <article
                className={`card goal-card${goal.status === "overdue" ? " goal-card--risk" : ""}`}
                key={goal.id}
              >
                <header className="goal-card__head">
                  <strong>{goal.title}</strong>
                  <StatusPill value={goal.status} />
                </header>
                <div className="progress">
                  <span style={{ width: `${goal.progress_percent}%` }} />
                </div>
                <dl>
                  <div>
                    <dt>Owner</dt>
                    <dd>{goal.owner?.display_name ?? "Unassigned"}</dd>
                  </div>
                  <div>
                    <dt>Deadline</dt>
                    <dd>{goal.deadline ?? "None"}</dd>
                  </div>
                  <div>
                    <dt>Topic</dt>
                    <dd>{goal.topic_id ?? "None"}</dd>
                  </div>
                  <div>
                    <dt>Nudge</dt>
                    <dd>{goal.next_nudge_at ? new Date(goal.next_nudge_at).toLocaleString() : "None"}</dd>
                  </div>
                </dl>
                {goal.latest_log && <p className="muted">{goal.latest_log}</p>}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No goals yet" />
        )}
      </Card>
    </section>
  );
}
