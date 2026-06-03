from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# The 5 attendance statuses mirror the HR sheet's Status dropdown verbatim.
AttendanceStatus = Literal["on_time", "late", "late_15", "no_show", "absent"]
ChaseState = Literal["none", "needs_chase", "chased", "resolved"]
GoalStatus = Literal["active", "overdue", "done", "paused"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorBody(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


DataT = TypeVar("DataT")


class Envelope(StrictModel, Generic[DataT]):
    """Standard response envelope used by every endpoint.

    On success, `data` holds the typed payload and `error` is `null`. On failure,
    `data` is `null` and `error` carries a machine-readable `code` plus a `message`.
    `meta` carries optional pagination/context (e.g. `week_start`, `week_end`).
    """

    data: DataT | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    error: ErrorBody | None = None


class IdResult(StrictModel):
    """Minimal acknowledgement returned by write endpoints that only confirm an id."""

    id: int


class SheetSyncResult(StrictModel):
    """Outcome of a Google Sheet attendance sync run."""

    id: int
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=120, examples=["admin"])
    password: str = Field(min_length=1, max_length=300, examples=["your-admin-password"])


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
    chase_state: ChaseState
    notes: str | None


class AttendanceCell(StrictModel):
    date: date
    status: AttendanceStatus | Literal["missing"]
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None


class AttendanceHistoryRow(StrictModel):
    person: PersonOut
    cells: list[AttendanceCell]


class WeeklySummaryRow(StrictModel):
    person: PersonOut
    on_time: int
    late: int
    late_15: int
    no_show: int
    absent: int


class ChasePatchRequest(StrictModel):
    chase_state: ChaseState = Field(examples=["chased"])


class ViperPersonRef(StrictModel):
    slug: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)


class ViperAttendanceUpsert(StrictModel):
    person: ViperPersonRef
    shift_date: date = Field(examples=["2026-06-03"])
    check_in_at: datetime | None = Field(default=None, examples=["2026-06-03T18:02:00+05:00"])
    check_out_at: datetime | None = None
    status: AttendanceStatus | None = Field(default=None, examples=["late_15"])
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


class ProjectTask(StrictModel):
    """A single checklist item for a project. `done` toggles completion."""

    text: str = Field(min_length=1, max_length=300)
    done: bool = False


class ProjectLogOut(StrictModel):
    id: int
    body: str
    created_at: datetime


class ViperProjectConditionUpsert(StrictModel):
    topic_id: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    last_activity_at: datetime | None = None
    # The Viper agent writes plain task strings; they are stored as open (done=false).
    open_items: list[str] = Field(default_factory=list)


class ProjectCreate(StrictModel):
    """Admin: create a new project. `topic_id` is auto-generated when omitted."""

    title: str = Field(min_length=1, max_length=180)
    topic_id: str | None = Field(default=None, max_length=80)
    summary: str | None = None
    open_items: list[ProjectTask] = Field(default_factory=list)


class ProjectUpdate(StrictModel):
    """Admin: patch a project. Every field is optional; omitted fields are left unchanged."""

    title: str | None = Field(default=None, min_length=1, max_length=180)
    summary: str | None = None
    open_items: list[ProjectTask] | None = None
    active: bool | None = None


class ProjectLogCreate(StrictModel):
    body: str = Field(min_length=1, max_length=2000)


class ProjectDeleted(StrictModel):
    topic_id: str


class ProjectConditionOut(StrictModel):
    topic_id: str
    title: str | None
    summary: str | None
    last_activity_at: datetime | None
    open_items: list[ProjectTask]
    logs: list[ProjectLogOut] = Field(default_factory=list)
    active: bool = True
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
