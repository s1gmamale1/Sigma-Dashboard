import { z } from "zod";
import type {
  Attendance,
  AttendanceHistoryRow,
  ChaseState,
  Envelope,
  Evaluation,
  Feedback,
  GoogleSheetImportResult,
  GoogleSheetPreview,
  Goal,
  Me,
  Overview,
  PerformanceRow,
  ProjectCondition,
  ProjectTask,
  Report,
  UserAccount,
  UserRole,
  WeeklySummaryRow
} from "./types";

export interface CreateUserBody {
  username: string;
  display_name: string;
  role: UserRole;
  temp_password: string;
  must_change_password?: boolean;
}

export interface UpdateUserBody {
  display_name?: string;
  role?: UserRole;
  active?: boolean;
}

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
  username: string;
  display_name: string;
  role: UserRole;
  must_change_password: boolean;
}

export async function apiFetchEnvelope<T, M = Record<string, unknown>>(
  path: string,
  token: string | null,
  init: RequestInit = {}
): Promise<{ data: T; meta: M }> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(path, { ...init, headers });
  const envelope = (await response.json()) as Envelope<T> & { meta: M };
  if (!response.ok || envelope.error) {
    throw new Error(envelope.error?.message ?? `Request failed with ${response.status}`);
  }
  return { data: envelope.data, meta: envelope.meta };
}

export async function apiFetch<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const { data } = await apiFetchEnvelope<T>(path, token, init);
  return data;
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
  reports: async (
    token: string,
    date: string
  ): Promise<{ reports: Report[]; latestReportDate: string | null }> => {
    const { data, meta } = await apiFetchEnvelope<Report[], { latest_report_date: string | null }>(
      `/api/v1/reports/daily?date=${date}`,
      token
    );
    return { reports: data, latestReportDate: meta?.latest_report_date ?? null };
  },
  performance: (token: string, from: string, to: string) =>
    apiFetch<PerformanceRow[]>(`/api/v1/performance?from=${from}&to=${to}`, token),
  evaluations: (token: string, from: string, to: string) =>
    apiFetch<Evaluation[]>(`/api/v1/evaluations?from=${from}&to=${to}`, token),
  feedback: (token: string, from: string, to: string) =>
    apiFetch<Feedback[]>(`/api/v1/feedback?from=${from}&to=${to}`, token),
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
    apiFetch<GoogleSheetImportResult>("/api/v1/google-sheet/import", token, { method: "POST" }),
  me: (token: string) => apiFetch<Me>("/api/v1/auth/me", token),
  changePassword: (token: string, current_password: string, new_password: string) =>
    apiFetch<Me>("/api/v1/auth/change-password", token, {
      method: "POST",
      body: JSON.stringify({ current_password, new_password })
    }),
  users: {
    list: (token: string) => apiFetch<UserAccount[]>("/api/v1/users", token),
    create: (token: string, body: CreateUserBody) =>
      apiFetch<UserAccount>("/api/v1/users", token, { method: "POST", body: JSON.stringify(body) }),
    update: (token: string, id: number, body: UpdateUserBody) =>
      apiFetch<UserAccount>(`/api/v1/users/${id}`, token, { method: "PATCH", body: JSON.stringify(body) }),
    resetPassword: (token: string, id: number, temp_password: string) =>
      apiFetch<UserAccount>(`/api/v1/users/${id}/reset-password`, token, {
        method: "POST",
        body: JSON.stringify({ temp_password })
      }),
    remove: (token: string, id: number) =>
      apiFetch<{ id: number }>(`/api/v1/users/${id}`, token, { method: "DELETE" })
  }
};
