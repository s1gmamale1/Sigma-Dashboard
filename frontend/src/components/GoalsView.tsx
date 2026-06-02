import type { Goal } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { StatusPill } from "./StatusPill";

export function GoalsView({ goals }: { goals: Goal[] }) {
  return (
    <section className="view-grid">
      <section className="panel wide">
        <header className="panel-header">
          <h2>Active goals</h2>
        </header>
        {goals.length ? (
          <div className="goal-grid">
            {goals.map((goal) => (
              <article className="goal-card" key={goal.id}>
                <header>
                  <strong>{goal.title}</strong>
                  <StatusPill value={goal.status} />
                </header>
                <div className="progress"><span style={{ width: `${goal.progress_percent}%` }} /></div>
                <dl>
                  <div><dt>Owner</dt><dd>{goal.owner?.display_name ?? "Unassigned"}</dd></div>
                  <div><dt>Deadline</dt><dd>{goal.deadline ?? "None"}</dd></div>
                  <div><dt>Topic</dt><dd>{goal.topic_id ?? "None"}</dd></div>
                  <div><dt>Nudge</dt><dd>{goal.next_nudge_at ? new Date(goal.next_nudge_at).toLocaleString() : "None"}</dd></div>
                </dl>
                {goal.latest_log ? <p>{goal.latest_log}</p> : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No goals yet" />
        )}
      </section>
    </section>
  );
}
