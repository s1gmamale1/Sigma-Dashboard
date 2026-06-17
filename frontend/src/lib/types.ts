export type Status = "on_time" | "late" | "late_15" | "no_show" | "absent" | "off_day";
export type ChaseState = "none" | "needs_chase" | "chased" | "resolved";
export type UserRole = "admin" | "manager" | "viewer";

export interface Me {
  username: string;
  display_name: string;
  role: UserRole;
  permissions: Record<string, string[]>;
  must_change_password: boolean;
}

export interface UserAccount {
  id: number;
  username: string;
  display_name: string;
  role: UserRole;
  active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
}

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
  chase_state: ChaseState;
  notes: string | null;
}

export interface AttendanceCell {
  date: string;
  status: Status | "missing";
  check_in_at: string | null;
  check_out_at: string | null;
}

export interface AttendanceHistoryRow {
  person: Person;
  cells: AttendanceCell[];
}

export interface WeeklySummaryRow {
  person: Person;
  on_time: number;
  late: number;
  late_15: number;
  no_show: number;
  absent: number;
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

export interface RatingPoint {
  date: string;
  rating: number;
}

export type CompositeGrade = "Under" | "Average" | "Good" | "Over";

export interface PerformanceRow {
  person: Person;
  average_rating: number | null;
  report_completion_rate: number;
  missing_days: number;
  assignment_count: number;
  top_accomplishment: string | null;
  rating_trend: RatingPoint[];
  avg_check_in: string | null;
  avg_check_out: string | null;
  on_time_count: number;
  late_count: number;
  late15_count: number;
  no_show_count: number;
  absent_count: number;
  attendance_days: number;
  punctuality_rate: number;
  compensates: boolean;
  avg_hours: number | null;
  composite_grade: CompositeGrade;
  composite_score: number;
}

export interface Evaluation {
  id: number;
  person: Person;
  period_start: string;
  period_end: string;
  grade: string;
  what: string;
  how: string;
  why: string;
  composite_score: number | null;
  updated_at: string | null;
}

export interface Feedback {
  id: number;
  person: Person;
  feedback_date: string;
  note: string;
  source: string | null;
  grade_adjustment: number;
  created_at: string;
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

export interface ProjectTask {
  text: string;
  done: boolean;
}

export interface ProjectLog {
  id: number;
  body: string;
  created_at: string;
}

export interface ProjectCondition {
  topic_id: string;
  title: string | null;
  summary: string | null;
  last_activity_at: string | null;
  open_items: ProjectTask[];
  logs: ProjectLog[];
  active: boolean;
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
