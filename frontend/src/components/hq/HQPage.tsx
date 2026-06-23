import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Boxes, FolderKanban, OctagonAlert, RefreshCw, Sliders } from "lucide-react";
import { hqApi, type HQHeartbeat, type HQProject } from "../../lib/hq";
import { parseServerDate } from "../../lib/dates";
import { EmptyState } from "../EmptyState";
import { ViewSkeleton } from "../ViewSkeleton";
import { SegmentedControl, type Segment } from "../SegmentedControl";
import { SourceHealth } from "./badges";
import { FleetView } from "./FleetView";
import { ProjectsView } from "./ProjectsView";
import { BlockersView } from "./BlockersView";
import { ActionsPanel } from "./ActionsPanel";

const SUBTABS: Segment[] = [
  { id: "fleet", label: "Fleet", icon: <Boxes size={16} /> },
  { id: "projects", label: "Projects", icon: <FolderKanban size={16} /> },
  { id: "blockers", label: "Blockers", icon: <OctagonAlert size={16} /> },
  { id: "control", label: "Control", icon: <Sliders size={16} /> }
];

const POLL_MS = 10000;

export function HQPage({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const [sub, setSub] = useState("fleet");

  const opts = { refetchInterval: POLL_MS } as const;
  const overview = useQuery({ queryKey: ["hq", "overview"], queryFn: () => hqApi.overview(token), ...opts });
  const workers = useQuery({ queryKey: ["hq", "workers"], queryFn: () => hqApi.workers(token), ...opts });
  const sessions = useQuery({ queryKey: ["hq", "sessions"], queryFn: () => hqApi.sessions(token), ...opts });
  const swarms = useQuery({ queryKey: ["hq", "swarms"], queryFn: () => hqApi.swarms(token), ...opts });
  const projects = useQuery({ queryKey: ["hq", "projects"], queryFn: () => hqApi.projects(token), ...opts });
  const tasks = useQuery({ queryKey: ["hq", "tasks"], queryFn: () => hqApi.tasks(token), ...opts });
  const blockers = useQuery({ queryKey: ["hq", "blockers"], queryFn: () => hqApi.blockers(token), ...opts });
  const heartbeats = useQuery({ queryKey: ["hq", "heartbeats"], queryFn: () => hqApi.heartbeats(token), ...opts });
  const actions = useQuery({ queryKey: ["hq", "actions"], queryFn: () => hqApi.actionsStatus(token), ...opts });

  const all = [overview, workers, sessions, swarms, projects, tasks, blockers, heartbeats];
  const errored = all.find((q) => q.error);
  const loading = all.some((q) => q.isLoading);

  const projectsById = useMemo(() => {
    const map = new Map<string, HQProject>();
    (projects.data?.data ?? []).forEach((p) => map.set(p.id, p));
    return map;
  }, [projects.data]);
  const projectName = (id: string | null) => (id ? projectsById.get(id)?.name ?? null : null);

  const hbByEntity = useMemo(() => {
    const map: Record<string, HQHeartbeat> = {};
    (heartbeats.data?.data ?? []).forEach((h) => {
      map[h.entity_id] = h;
    });
    return map;
  }, [heartbeats.data]);

  if (errored) {
    const message = errored.error instanceof Error ? errored.error.message : "Unable to load HQ";
    return (
      <EmptyState
        title={message}
        icon={<AlertTriangle aria-hidden="true" size={22} />}
        action={
          <button className="primary-button compact" onClick={() => queryClient.invalidateQueries({ queryKey: ["hq"] })}>
            <RefreshCw size={16} aria-hidden="true" /> Retry
          </button>
        }
      />
    );
  }
  if (loading || !overview.data) return <ViewSkeleton />;

  const sources = overview.data.data.sources;
  const generatedAt = overview.data.data.generated_at;

  return (
    <div className="hq">
      <div className="hq-controlbar">
        <SegmentedControl items={SUBTABS} value={sub} onChange={setSub} ariaLabel="HQ sections" />
        <div className="hq-sources">
          {Object.entries(sources).map(([name, healthy]) => (
            <SourceHealth key={name} name={name} healthy={healthy} />
          ))}
          <span className="muted hq-updated">
            updated{" "}
            {new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
              parseServerDate(generatedAt)
            )}
          </span>
          {(() => {
            const a = actions.data?.data;
            const armed = !!a?.enabled && !!a?.signoff_configured;
            return (
              <span
                className={`hq-control-pill hq-control-pill--${armed ? "armed" : "readonly"}`}
                title={
                  armed
                    ? "Control armed — actions require an operator-minted X-Sigma-Signoff token" +
                      (a?.destructive_enabled ? " (destructive enabled)" : " (non-destructive only)")
                    : "Read-only — control actions disabled (403)"
                }
              >
                {armed ? "control: armed · signed" : "control: read-only"}
              </span>
            );
          })()}
        </div>
      </div>

      {sub === "fleet" && (
        <FleetView
          overview={overview.data.data}
          workers={workers.data?.data ?? []}
          sessions={sessions.data?.data ?? []}
          swarms={swarms.data?.data ?? []}
          hbByEntity={hbByEntity}
          projectName={projectName}
        />
      )}
      {sub === "projects" && (
        <ProjectsView
          projects={projects.data?.data ?? []}
          tasks={tasks.data?.data ?? []}
          projectName={projectName}
        />
      )}
      {sub === "blockers" && (
        <BlockersView blockers={blockers.data?.data ?? []} heartbeats={heartbeats.data?.data ?? []} />
      )}
      {sub === "control" && actions.data && (
        <ActionsPanel token={token} capabilities={actions.data.data} />
      )}
    </div>
  );
}
