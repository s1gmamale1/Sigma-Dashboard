// HQ control-plane API client + types. Mirrors backend/app/hq/models.py.
// All timestamps are naive-UTC strings — render via parseServerDate, never new Date.
import { apiFetchEnvelope } from "./api";

export type WorkerStatus = "idle" | "running" | "blocked" | "offline";
export type TaskStatus = "todo" | "in_progress" | "review" | "done" | "blocked";
export type Severity = "low" | "medium" | "high" | "critical";

export type HQSourceHealth = Record<string, boolean>;
export interface HQMeta {
  generated_at: string;
  sources: HQSourceHealth;
}
export interface HQResult<T> {
  data: T;
  meta: HQMeta;
}

export interface HQProject {
  id: string;
  source: string;
  source_id: string;
  name: string;
  slug: string;
  owner: string | null;
  status: string | null;
  repo_path: string | null;
  updated_at: string | null;
}

export interface HQWorker {
  id: string;
  source: string;
  source_id: string;
  name: string;
  kind: string;
  model: string | null;
  owner: string | null;
  status: WorkerStatus;
  project_id: string | null;
  session_id: string | null;
  task_id: string | null;
  worktree_path: string | null;
  last_heartbeat: string | null;
}

export interface HQSession {
  id: string;
  source: string;
  source_id: string;
  worker_id: string | null;
  project_id: string | null;
  status: string | null;
  started_at: string | null;
  last_activity: string | null;
  transcript_ref: string | null;
}

export interface HQSwarm {
  id: string;
  source: string;
  source_id: string;
  name: string;
  topology: string | null;
  coordinator: string | null;
  member_worker_ids: string[];
  project_id: string | null;
  status: string | null;
  last_heartbeat: string | null;
}

export interface HQTask {
  id: string;
  source: string;
  source_id: string;
  title: string;
  project_id: string | null;
  assignee_worker_id: string | null;
  status: TaskStatus;
  priority: number | null;
  blocker_ids: string[];
  updated_at: string | null;
}

export interface HQBlocker {
  id: string;
  source: string;
  source_id: string;
  title: string;
  severity: Severity;
  entity_type: string | null;
  entity_id: string | null;
  owner: string | null;
  status: string;
  opened_at: string | null;
}

export interface HQHeartbeat {
  entity_type: string;
  entity_id: string;
  source: string;
  ts: string | null;
  staleness_seconds: number | null;
  healthy: boolean;
}

export interface HQOverview {
  workers_total: number;
  workers_running: number;
  workers_blocked: number;
  workers_offline: number;
  sessions_active: number;
  swarms_active: number;
  tasks_open: number;
  tasks_blocked: number;
  blockers_open: number;
  sources: HQSourceHealth;
  generated_at: string;
}

async function get<T>(path: string, token: string): Promise<HQResult<T>> {
  const { data, meta } = await apiFetchEnvelope<T, HQMeta>(`/api/v1/hq/${path}`, token);
  return { data, meta };
}

export const hqApi = {
  overview: (token: string) => get<HQOverview>("overview", token),
  workers: (token: string) => get<HQWorker[]>("workers", token),
  sessions: (token: string) => get<HQSession[]>("sessions", token),
  swarms: (token: string) => get<HQSwarm[]>("swarms", token),
  projects: (token: string) => get<HQProject[]>("projects", token),
  tasks: (token: string) => get<HQTask[]>("tasks", token),
  blockers: (token: string) => get<HQBlocker[]>("blockers", token),
  heartbeats: (token: string) => get<HQHeartbeat[]>("heartbeats", token)
};
