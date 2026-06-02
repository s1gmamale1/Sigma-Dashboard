import { Clock3 } from "lucide-react";
import type { ProjectCondition } from "../lib/types";
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";
import { EmptyState } from "./EmptyState";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const MONTH = 30 * DAY;

function relativeTime(iso: string | null): string {
  if (!iso) return "No activity";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "No activity";
  const diff = Date.now() - then;
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  if (diff < MONTH) return `${Math.floor(diff / DAY)}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function ProjectConditionView({ conditions }: { conditions: ProjectCondition[] }) {
  return (
    <section className="view-grid">
      <Card wide>
        <SectionHeader title="Project condition" />
        {conditions.length ? (
          <div className="topic-grid">
            {conditions.map((condition) => (
              <article className="card topic-card" key={condition.topic_id}>
                <header className="topic-card__head">
                  <strong>{condition.title ?? `Topic ${condition.topic_id}`}</strong>
                  <span className="topic-chip">#{condition.topic_id}</span>
                </header>
                <p className="muted">{condition.summary ?? "No condition summary yet"}</p>
                <div className="topic-meta">
                  <Clock3 size={16} aria-hidden="true" />
                  <span className="muted">{relativeTime(condition.last_activity_at)}</span>
                </div>
                {condition.open_items.length ? (
                  <ul className="checklist">
                    {condition.open_items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <small className="muted">No open items</small>
                )}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No project topics" />
        )}
      </Card>
    </section>
  );
}
