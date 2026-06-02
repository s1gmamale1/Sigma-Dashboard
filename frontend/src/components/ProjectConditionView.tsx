import { Clock3 } from "lucide-react";
import type { ProjectCondition } from "../lib/types";
import { EmptyState } from "./EmptyState";

export function ProjectConditionView({ conditions }: { conditions: ProjectCondition[] }) {
  return (
    <section className="view-grid">
      <section className="panel wide">
        <header className="panel-header">
          <h2>Project condition</h2>
        </header>
        {conditions.length ? (
          <div className="topic-grid">
            {conditions.map((condition) => (
              <article className="topic-card" key={condition.topic_id}>
                <header>
                  <strong>{condition.title ?? `Topic ${condition.topic_id}`}</strong>
                  <span>#{condition.topic_id}</span>
                </header>
                <p>{condition.summary ?? "No condition summary yet"}</p>
                <div className="topic-meta">
                  <Clock3 size={16} aria-hidden="true" />
                  <span>{condition.last_activity_at ? new Date(condition.last_activity_at).toLocaleString() : "No activity"}</span>
                </div>
                {condition.open_items.length ? (
                  <ul>
                    {condition.open_items.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                ) : (
                  <small>No open items</small>
                )}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No project topics" />
        )}
      </section>
    </section>
  );
}

