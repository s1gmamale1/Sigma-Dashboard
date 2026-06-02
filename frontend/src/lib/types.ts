export type Status = "in" | "late" | "charged" | "no_show" | "excused";
export type ChaseState = "none" | "needs_chase" | "chased" | "resolved";

export interface Envelope<T> {
  data: T;
  meta: Record<string, unknown>;
  error: null | { code: string; message: string; details: Record<string, unknown> };
}

export interface Person {
  id: number;
  slug: string;
  display_name: string;
  active: boolean;
  sort_order: number;
}

export interface Attendance {
  id: number;
  person: Person;
  shift_date: string;
  check_in_at: string | null;
  check_out_at: string | null;
  status: Status;
  minutes_late: number;
  charged: boolean;
  charge_amount_uzs: number;
  charge_reason: string;
  chase_state: ChaseState;
  notes: string | null;
}

export interface AttendanceCell {
  date: string;
  status: Status | "missing";
  check_in_at: string | null;
  check_out_at: string | null;
  charged: boolean;
  charge_amount_uzs: number;
}

export interface AttendanceHistoryRow {
  person: Person;
  cells: AttendanceCell[];
}

export interface WeeklySummaryRow {
  person: Person;
  lates: number;
  free_late_used: boolean;
  charged_count: number;
  total_charge_uzs: number;
}

export interface Report {
  id: number;
  person: Person;
  report_date: string;
  summary: string;
  extras: string | null;
  rating: number | null;
  missing: boolean;
  source_topic: string | null;
  assignments: string[];
}

export interface PerformanceRow {
  person: Person;
  average_rating: number | null;
  report_completion_rate: number;
  missing_days: number;
  assignment_count: number;
}

export interface Goal {
  id: number;
  slug: string;
  title: string;
  owner: Person | null;
  topic_id: string | null;
  deadline: string | null;
  status: "active" | "overdue" | "done" | "paused";
  progress_percent: number;
  last_update_at: string | null;
  next_nudge_at: string | null;
  latest_log: string | null;
}

export interface ProjectCondition {
  topic_id: string;
  title: string | null;
  summary: string | null;
  last_activity_at: string | null;
  open_items: string[];
  updated_at: string | null;
}

export interface Overview {
  today_attendance: Attendance[];
  weekly_summary: WeeklySummaryRow[];
  missing_reports_count: number;
  at_risk_goals: Goal[];
  stale_project_topics: ProjectCondition[];
}

export interface GoogleSheetTabPreview {
  title: string;
  row_count: number;
  column_count: number;
  sample_range: string;
  values: string[][];
}

export interface GoogleSheetPreview {
  spreadsheet_id: string;
  spreadsheet_title: string;
  configured_name: string;
  tabs: GoogleSheetTabPreview[];
}

export interface GoogleSheetImportResult {
  spreadsheet_id: string;
  spreadsheet_title: string;
  imported: Record<string, number>;
  skipped_tabs: string[];
  notes: string[];
}
