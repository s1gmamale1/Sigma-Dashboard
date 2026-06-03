import { z } from "zod";
import type {
  Attendance,
  AttendanceHistoryRow,
  ChaseState,
  Envelope,
  GoogleSheetImportResult,
  GoogleSheetPreview,
  Goal,
  Overview,
  PerformanceRow,
  ProjectCondition,
  ProjectTask,
  Report,
  WeeklySummaryRow
} from "./types";

export interface CreateProjectBody {
  title: string;
  topic_id?: string;
  summary?: string;
  open_items: ProjectTask[];
}

export interface UpdateProjectBody {
  title?: string;
  summary?: string;
  open_items?: ProjectTask[];
  active?: boolean;
}

const loginSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1)
});

export interface Session {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
}

export async function apiFetch<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(path, { ...init, headers });
  const envelope = (await response.json()) as Envelope<T>;
  if (!response.ok || envelope.error) {
    throw new Error(envelope.error?.message ?? `Request failed with ${response.status}`);
  }
  return envelope.data;
}

export async function login(username: string, password: string): Promise<Session> {
  const payload = loginSchema.parse({ username, password });
  return apiFetch<Session>("/api/v1/auth/login", null, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export const api = {
  overview: (token: string, shiftDate: string) =>
    apiFetch<Overview>(`/api/v1/dashboard/overview?shift_date=${shiftDate}`, token),
  today: (token: string, shiftDate: string) =>
    apiFetch<Attendance[]>(`/api/v1/attendance/today?shift_date=${shiftDate}`, token),
  history: (token: string, from: string, to: string) =>
    apiFetch<AttendanceHistoryRow[]>(`/api/v1/attendance/history?from=${from}&to=${to}`, token),
  weekly: (token: string, weekStart: string) =>
    apiFetch<WeeklySummaryRow[]>(`/api/v1/attendance/weekly-summary?week_start=${weekStart}`, token),
  patchChase: (token: string, id: number, chase_state: ChaseState) =>
    apiFetch<Attendance>(`/api/v1/attendance/${id}/chase-state`, token, {
      method: "PATCH",
      body: JSON.stringify({ chase_state })
    }),
  reports: (token: string, date: string) => apiFetch<Report[]>(`/api/v1/reports/daily?date=${date}`, token),
  performance: (token: string, from: string, to: string) =>
    apiFetch<PerformanceRow[]>(`/api/v1/performance?from=${from}&to=${to}`, token),
  goals: (token: string) => apiFetch<Goal[]>("/api/v1/goals", token),
  projectConditions: (token: string, includeArchived = false) =>
    apiFetch<ProjectCondition[]>(
      `/api/v1/project-conditions${includeArchived ? "?include_archived=true" : ""}`,
      token
    ),
  createProject: (token: string, body: CreateProjectBody) =>
    apiFetch<ProjectCondition>("/api/v1/projects", token, {
      method: "POST",
      body: JSON.stringify(body)
    }),
  updateProject: (token: string, topicId: string, body: UpdateProjectBody) =>
    apiFetch<ProjectCondition>(`/api/v1/projects/${encodeURIComponent(topicId)}`, token, {
      method: "PATCH",
      body: JSON.stringify(body)
    }),
  deleteProject: (token: string, topicId: string) =>
    apiFetch<{ topic_id: string }>(`/api/v1/projects/${encodeURIComponent(topicId)}`, token, {
      method: "DELETE"
    }),
  addProjectLog: (token: string, topicId: string, bodyText: string) =>
    apiFetch<ProjectCondition>(`/api/v1/projects/${encodeURIComponent(topicId)}/logs`, token, {
      method: "POST",
      body: JSON.stringify({ body: bodyText })
    }),
  deleteProjectLog: (token: string, topicId: string, logId: number) =>
    apiFetch<ProjectCondition>(
      `/api/v1/projects/${encodeURIComponent(topicId)}/logs/${logId}`,
      token,
      { method: "DELETE" }
    ),
  syncAttendance: (token: string) => apiFetch<Record<string, unknown>>("/api/v1/sheets/sync/attendance", token, { method: "POST" }),
  googleSheetPreview: (token: string) => apiFetch<GoogleSheetPreview>("/api/v1/google-sheet/preview", token),
  googleSheetImport: (token: string) =>
    apiFetch<GoogleSheetImportResult>("/api/v1/google-sheet/import", token, { method: "POST" })
};
