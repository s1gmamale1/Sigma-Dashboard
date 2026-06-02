from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AttendanceStatus = Literal["in", "late", "charged", "no_show", "excused"]
ChargeReason = Literal["none", "late_after_grace", "second_late_week", "no_show", "manual_policy"]
ChaseState = Literal["none", "needs_chase", "chased", "resolved"]
GoalStatus = Literal["active", "overdue", "done", "paused"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorBody(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class Envelope(StrictModel):
    data: Any = None
    meta: dict[str, Any] = Field(default_factory=dict)
    error: ErrorBody | None = None


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=300)


class LoginResponse(StrictModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class PersonOut(StrictModel):
    id: int
    slug: str
    display_name: str
    active: bool
    sort_order: int


class AttendanceOut(StrictModel):
    id: int
    person: PersonOut
    shift_date: date
    check_in_at: datetime | None
    check_out_at: datetime | None
    status: AttendanceStatus
    minutes_late: int
    charged: bool
    charge_amount_uzs: int
    charge_reason: ChargeReason
    chase_state: ChaseState
    notes: str | None


class AttendanceCell(StrictModel):
    date: date
    status: AttendanceStatus | Literal["missing"]
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    charged: bool = False
    charge_amount_uzs: int = 0


class AttendanceHistoryRow(StrictModel):
    person: PersonOut
    cells: list[AttendanceCell]


class WeeklySummaryRow(StrictModel):
    person: PersonOut
    lates: int
    free_late_used: bool
    charged_count: int
    total_charge_uzs: int


class ChasePatchRequest(StrictModel):
    chase_state: ChaseState


class ViperPersonRef(StrictModel):
    slug: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)


class ViperAttendanceUpsert(StrictModel):
    person: ViperPersonRef
    shift_date: date
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    status: AttendanceStatus | None = None
    chase_state: ChaseState = "none"
    notes: str | None = None


class ViperReportUpsert(StrictModel):
    person: ViperPersonRef
    report_date: date
    summary: str = Field(min_length=1)
    extras: str | None = None
    rating: int | None = Field(default=None, ge=1, le=4)
    missing: bool = False
    source_topic: str | None = None


class ReportOut(StrictModel):
    id: int
    person: PersonOut
    report_date: date
    summary: str
    extras: str | None
    rating: int | None
    missing: bool
    source_topic: str | None
    assignments: list[str] = Field(default_factory=list)


class PerformanceRow(StrictModel):
    person: PersonOut
    average_rating: float | None
    report_completion_rate: float
    missing_days: int
    assignment_count: int


class ViperGoalUpsert(StrictModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    owner_slug: str | None = None
    topic_id: str | None = None
    deadline: date | None = None
    status: GoalStatus = "active"
    progress_percent: int = Field(default=0, ge=0, le=100)
    last_update_at: datetime | None = None
    next_nudge_at: datetime | None = None
    progress_log: str | None = None


class GoalOut(StrictModel):
    id: int
    slug: str
    title: str
    owner: PersonOut | None
    topic_id: str | None
    deadline: date | None
    status: GoalStatus
    progress_percent: int
    last_update_at: datetime | None
    next_nudge_at: datetime | None
    latest_log: str | None


class ViperProjectConditionUpsert(StrictModel):
    topic_id: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    last_activity_at: datetime | None = None
    open_items: list[str] = Field(default_factory=list)


class ProjectConditionOut(StrictModel):
    topic_id: str
    title: str | None
    summary: str | None
    last_activity_at: datetime | None
    open_items: list[str]
    updated_at: datetime | None


class DashboardOverview(StrictModel):
    today_attendance: list[AttendanceOut]
    weekly_summary: list[WeeklySummaryRow]
    missing_reports_count: int
    at_risk_goals: list[GoalOut]
    stale_project_topics: list[ProjectConditionOut]


class GoogleSheetTabPreview(StrictModel):
    title: str
    row_count: int
    column_count: int
    sample_range: str
    values: list[list[str]]


class GoogleSheetPreview(StrictModel):
    spreadsheet_id: str
    spreadsheet_title: str
    configured_name: str
    tabs: list[GoogleSheetTabPreview]


class GoogleSheetImportResult(StrictModel):
    spreadsheet_id: str
    spreadsheet_title: str
    imported: dict[str, int]
    skipped_tabs: list[str]
    notes: list[str]
