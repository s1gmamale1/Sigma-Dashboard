import { useState } from "react";
import { Archive, Clock3, Plus } from "lucide-react";
import { parseServerDate } from "../lib/dates";
import type { ProjectCondition } from "../lib/types";
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";
import { EmptyState } from "./EmptyState";
import { ProjectEditor } from "./ProjectEditor";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const MONTH = 30 * DAY;

function relativeTime(iso: string | null): string {
  if (!iso) return "No activity";
  const then = parseServerDate(iso).getTime();
  if (Number.isNaN(then)) return "No activity";
  const diff = Date.now() - then;
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  if (diff < MONTH) return `${Math.floor(diff / DAY)}d ago`;
  return parseServerDate(iso).toLocaleDateString();
}

type EditorState = null | "new" | ProjectCondition;

export function ProjectConditionView({
  token,
  conditions,
  showArchived,
  onShowArchived
}: {
  token: string;
  conditions: ProjectCondition[];
  showArchived: boolean;
  onShowArchived: (next: boolean) => void;
}) {
  const [editor, setEditor] = useState<EditorState>(null);

  return (
    <section className="view-grid">
      <Card wide>
        <SectionHeader
          title="Project condition"
          actions={
            <span className="projects-toolbar">
              <button
                type="button"
                className="ghost-button"
                onClick={() => onShowArchived(!showArchived)}
                aria-pressed={showArchived}
              >
                <Archive size={16} aria-hidden="true" /> {showArchived ? "Hide archived" : "Show archived"}
              </button>
              <button type="button" className="primary-button compact" onClick={() => setEditor("new")}>
                <Plus size={16} aria-hidden="true" /> New project
              </button>
            </span>
          }
        />
        {conditions.length ? (
          <div className="topic-grid">
            {conditions.map((condition) => {
              const openCount = condition.open_items.filter((item) => !item.done).length;
              const archived = !condition.active;
              return (
                <div
                  role="button"
                  tabIndex={0}
                  className={`card topic-card topic-card--button${archived ? " topic-card--archived" : ""}`}
                  key={condition.topic_id}
                  onClick={() => setEditor(condition)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setEditor(condition);
                    }
                  }}
                >
                  <span className="topic-card__head">
                    <strong>{condition.title ?? `Topic ${condition.topic_id}`}</strong>
                    <span className={`topic-chip${archived ? " topic-chip--archived" : ""}`}>
                      {archived ? "Archived" : `#${condition.topic_id}`}
                    </span>
                  </span>
                  <span className="muted topic-card__summary">
                    {condition.summary ?? "No condition summary yet"}
                  </span>
                  <span className="topic-meta">
                    <Clock3 size={16} aria-hidden="true" />
                    <span className="muted">{relativeTime(condition.last_activity_at)}</span>
                    {condition.open_items.length ? (
                      <span className="muted">
                        {" · "}
                        {openCount} open
                      </span>
                    ) : null}
                  </span>
                  {condition.open_items.length ? (
                    <ul className="checklist">
                      {condition.open_items.map((item, index) => (
                        <li
                          className={`checklist__item${item.done ? " is-done" : ""}`}
                          key={`${index}-${item.text}`}
                        >
                          <span className="checklist__box" aria-hidden="true">
                            {item.done ? "✓" : ""}
                          </span>
                          <span className="checklist__text">{item.text}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <small className="muted">No open items</small>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState title={showArchived ? "No archived projects" : "No project topics"} />
        )}
      </Card>

      {editor !== null ? (
        <ProjectEditor
          token={token}
          project={editor === "new" ? null : editor}
          onClose={() => setEditor(null)}
        />
      ) : null}
    </section>
  );
}
