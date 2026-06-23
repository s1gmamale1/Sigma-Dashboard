import type { HQProject, HQTask, TaskStatus } from "../../lib/hq";
import { Card } from "../Card";
import { EmptyState } from "../EmptyState";
import { SectionHeader } from "../SectionHeader";
import { SourceBadge } from "./badges";

const COLUMNS: { id: TaskStatus; label: string }[] = [
  { id: "todo", label: "To do" },
  { id: "in_progress", label: "In progress" },
  { id: "review", label: "Review" },
  { id: "blocked", label: "Blocked" },
  { id: "done", label: "Done" }
];

export function ProjectsView({
  projects,
  tasks,
  projectName
}: {
  projects: HQProject[];
  tasks: HQTask[];
  projectName: (id: string | null) => string | null;
}) {
  return (
    <section className="view-grid">
      <Card wide className="tile">
        <SectionHeader title={`Projects (${projects.length})`} />
        {projects.length ? (
          <div className="hq-list">
            {projects.map((p) => (
              <div className="hq-listrow" key={p.id}>
                <div className="hq-listrow__main">
                  <strong>{p.name}</strong>
                  <span className="muted">
                    {p.status ?? "—"}
                    {p.owner ? ` · @${p.owner}` : ""}
                  </span>
                </div>
                <SourceBadge source={p.source} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No projects reported" />
        )}
      </Card>

      <Card wide className="tile">
        <SectionHeader title={`Tasks (${tasks.length})`} />
        {tasks.length ? (
          <div className="hq-board">
            {COLUMNS.map((col) => {
              const items = tasks.filter((t) => t.status === col.id);
              return (
                <div className="hq-board__col" key={col.id}>
                  <div className="hq-board__head">
                    {col.label} <span className="muted">{items.length}</span>
                  </div>
                  {items.map((t) => (
                    <div className={`hq-card hq-card--${t.status}`} key={t.id}>
                      <strong>{t.title}</strong>
                      <span className="muted">{projectName(t.project_id) ?? "—"}</span>
                      <SourceBadge source={t.source} />
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState title="No live task source yet — tasks are spec-only (SigmaControl exposes no task read API)" />
        )}
      </Card>
    </section>
  );
}
