import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import create_access_token, require_admin, require_viper, verify_password
from .config import Settings, get_settings
from .db import get_db
from .google_sheets import GoogleSheetError, get_sheet_preview, import_google_sheet_dashboard_data
from .models import Assignment, AttendanceRecord, Goal, GoalLog, Person, ProjectCondition, ProjectTopic, Report
from .schemas import (
    AttendanceCell,
    AttendanceHistoryRow,
    AttendanceOut,
    ChasePatchRequest,
    DashboardOverview,
    Envelope,
    GoalOut,
    GoogleSheetImportResult,
    GoogleSheetPreview,
    IdResult,
    LoginRequest,
    LoginResponse,
    PerformanceRow,
    PersonOut,
    ProjectConditionOut,
    ReportOut,
    SheetSyncResult,
    ViperAttendanceUpsert,
    ViperGoalUpsert,
    ViperProjectConditionUpsert,
    ViperReportUpsert,
    WeeklySummaryRow,
)
from .services import (
    apply_goal_status,
    date_span,
    sync_attendance_to_sheet,
    upsert_attendance,
    upsert_goal,
    upsert_project_condition,
    upsert_report,
    week_bounds,
)

router = APIRouter(prefix="/api/v1")


def _err(description: str) -> dict:
    """Document an error response as the standard envelope (data null, error populated)."""
    return {"model": Envelope, "description": description}


UNAUTHORIZED = {401: _err("Missing or invalid admin bearer token.")}
VIPER_UNAUTHORIZED = {401: _err("Missing or invalid `X-Viper-Token`.")}
NOT_FOUND = {404: _err("Resource not found.")}
INVALID_RANGE = {422: _err("Invalid query parameters (e.g. `to` before `from`).")}
SHEET_ERROR = {400: _err("Google Sheet could not be read or imported.")}


def ok(data: object, meta: dict | None = None) -> Envelope:
    return Envelope(data=data, meta=meta or {}, error=None)


def person_out(person: Person) -> PersonOut:
    return PersonOut.model_validate(person)


def attendance_out(record: AttendanceRecord) -> AttendanceOut:
    return AttendanceOut(
        id=record.id,
        person=person_out(record.person),
        shift_date=record.shift_date,
        check_in_at=record.check_in_at,
        check_out_at=record.check_out_at,
        status=record.status,  # type: ignore[arg-type]
        minutes_late=record.minutes_late,
        charged=record.charged,
        charge_amount_uzs=record.charge_amount_uzs,
        charge_reason=record.charge_reason,  # type: ignore[arg-type]
        chase_state=record.chase_state,  # type: ignore[arg-type]
        notes=record.notes,
    )


def goal_out(db: Session, goal: Goal) -> GoalOut:
    owner = db.get(Person, goal.owner_person_id) if goal.owner_person_id else None
    latest_log = db.scalar(
        select(GoalLog.body).where(GoalLog.goal_id == goal.id).order_by(GoalLog.created_at.desc()).limit(1)
    )
    return GoalOut(
        id=goal.id,
        slug=goal.slug,
        title=goal.title,
        owner=person_out(owner) if owner else None,
        topic_id=goal.topic_id,
        deadline=goal.deadline,
        status=apply_goal_status(goal),  # type: ignore[arg-type]
        progress_percent=goal.progress_percent,
        last_update_at=goal.last_update_at,
        next_nudge_at=goal.next_nudge_at,
        latest_log=latest_log,
    )


def project_condition_out(topic: ProjectTopic, condition: ProjectCondition | None) -> ProjectConditionOut:
    return ProjectConditionOut(
        topic_id=topic.topic_id,
        title=topic.title,
        summary=condition.summary if condition else None,
        last_activity_at=condition.last_activity_at if condition else None,
        open_items=json.loads(condition.open_items_json) if condition else [],
        updated_at=condition.updated_at if condition else None,
    )


@router.post(
    "/auth/login",
    response_model=Envelope[LoginResponse],
    tags=["Auth"],
    summary="Log in as admin",
    responses={**UNAUTHORIZED},
)
def login(payload: LoginRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Envelope:
    """Exchange an admin username + password for a bearer JWT.

    Returns `data.access_token` (send it as `Authorization: Bearer <token>`) and `data.expires_at`.
    """
    if payload.username != settings.admin_username or not verify_password(settings, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token, expires_at = create_access_token(settings, settings.admin_username)
    return ok(LoginResponse(access_token=token, expires_at=expires_at))


@router.get(
    "/dashboard/overview",
    response_model=Envelope[DashboardOverview],
    tags=["Dashboard"],
    summary="Dashboard overview",
    responses={**UNAUTHORIZED},
)
def dashboard_overview(
    shift_date: date | None = Query(default=None, description="Shift day (YYYY-MM-DD); defaults to today."),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """Aggregated home view for a shift day: tonight's attendance, the weekly charge
    summary, the count of missing reports, at-risk goals, and stale project topics."""
    current = shift_date or date.today()
    week_start, week_end = week_bounds(current)
    today = get_today_attendance(current, db, _).data
    weekly = get_weekly_summary(week_start, db, _).data
    missing_reports_count = db.scalar(
        select(func.count(Report.id)).where(Report.report_date == current, Report.missing.is_(True))
    ) or 0
    goals = list(db.scalars(select(Goal).order_by(Goal.deadline.asc().nullslast()).limit(8)))
    at_risk_goals = [goal_out(db, goal) for goal in goals if apply_goal_status(goal) in {"active", "overdue"}]
    conditions = get_project_conditions(db, _).data
    stale = [
        item
        for item in conditions
        if item.updated_at is None or item.updated_at.date() < current - timedelta(days=2)
    ]
    return ok(
        DashboardOverview(
            today_attendance=today,
            weekly_summary=weekly,
            missing_reports_count=missing_reports_count,
            at_risk_goals=at_risk_goals,
            stale_project_topics=stale,
        )
    )


@router.get(
    "/attendance/today",
    response_model=Envelope[list[AttendanceOut]],
    tags=["Attendance"],
    summary="Tonight's attendance",
    responses={**UNAUTHORIZED},
)
def get_today_attendance(
    shift_date: date | None = Query(default=None, description="Shift day (YYYY-MM-DD); defaults to today."),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """The attendance record for each person on the given shift day, ordered by roster."""
    current = shift_date or date.today()
    records = list(
        db.scalars(
            select(AttendanceRecord)
            .where(AttendanceRecord.shift_date == current)
            .join(Person)
            .order_by(Person.sort_order, Person.display_name)
        )
    )
    return ok([attendance_out(record) for record in records])


@router.get(
    "/attendance/history",
    response_model=Envelope[list[AttendanceHistoryRow]],
    tags=["Attendance"],
    summary="Attendance history grid",
    responses={**UNAUTHORIZED, **INVALID_RANGE},
)
def get_attendance_history(
    start: date = Query(alias="from", description="Inclusive start day (YYYY-MM-DD)."),
    end: date = Query(alias="to", description="Inclusive end day (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """A rows=people × cols=days grid over `[from, to]`. Days with no record return a
    `missing` cell, so every person has a full, gap-free row."""
    if end < start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="to must be after from")
    people = list(db.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.sort_order)))
    records = list(
        db.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.shift_date >= start,
                AttendanceRecord.shift_date <= end,
            )
        )
    )
    by_key = {(record.person_id, record.shift_date): record for record in records}
    rows = []
    for person in people:
        cells = []
        for day in date_span(start, end):
            record = by_key.get((person.id, day))
            cells.append(
                AttendanceCell(
                    date=day,
                    status=record.status if record else "missing",  # type: ignore[arg-type]
                    check_in_at=record.check_in_at if record else None,
                    check_out_at=record.check_out_at if record else None,
                    charged=record.charged if record else False,
                    charge_amount_uzs=record.charge_amount_uzs if record else 0,
                )
            )
        rows.append(AttendanceHistoryRow(person=person_out(person), cells=cells))
    return ok(rows)


@router.get(
    "/attendance/weekly-summary",
    response_model=Envelope[list[WeeklySummaryRow]],
    tags=["Attendance"],
    summary="Weekly charge summary",
    responses={**UNAUTHORIZED},
)
def get_weekly_summary(
    week_start: date = Query(description="Monday of the target week (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """Per-person lates, charged count, and total charge (UZS) for the Mon–Sun week
    beginning at `week_start`. `meta` echoes the resolved `week_start`/`week_end`."""
    week_end = week_start + timedelta(days=6)
    people = list(db.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.sort_order)))
    rows: list[WeeklySummaryRow] = []
    for person in people:
        records = list(
            db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.person_id == person.id,
                    AttendanceRecord.shift_date >= week_start,
                    AttendanceRecord.shift_date <= week_end,
                )
            )
        )
        lates = sum(1 for record in records if record.minutes_late > 0)
        charged = [record for record in records if record.charged]
        rows.append(
            WeeklySummaryRow(
                person=person_out(person),
                lates=lates,
                free_late_used=any(record.minutes_late > 0 and not record.charged for record in records),
                charged_count=len(charged),
                total_charge_uzs=sum(record.charge_amount_uzs for record in charged),
            )
        )
    return ok(rows, meta={"week_start": week_start.isoformat(), "week_end": week_end.isoformat()})


@router.patch(
    "/attendance/{record_id}/chase-state",
    response_model=Envelope[AttendanceOut],
    tags=["Attendance"],
    summary="Update chase state",
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def patch_chase_state(
    record_id: int,
    payload: ChasePatchRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """Set the chase state (`none` / `needs_chase` / `chased` / `resolved`) on one
    attendance record and return the updated record."""
    record = db.get(AttendanceRecord, record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")
    record.chase_state = payload.chase_state
    db.commit()
    db.refresh(record)
    return ok(attendance_out(record))


@router.get(
    "/reports/daily",
    response_model=Envelope[list[ReportOut]],
    tags=["Reports"],
    summary="Daily reports",
    responses={**UNAUTHORIZED},
)
def get_daily_reports(
    report_date: date = Query(alias="date", description="Report day (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """Each person's report for the given day — summary, extras, rating (1–4), missing
    flag, source topic, and their active assignments."""
    reports = list(
        db.scalars(
            select(Report).where(Report.report_date == report_date).join(Person).order_by(Person.sort_order)
        )
    )
    result = []
    for report in reports:
        assignments = list(
            db.scalars(
                select(Assignment.assignment).where(
                    Assignment.person_id == report.person_id,
                    Assignment.active.is_(True),
                )
            )
        )
        result.append(
            ReportOut(
                id=report.id,
                person=person_out(report.person),
                report_date=report.report_date,
                summary=report.summary,
                extras=report.extras,
                rating=report.rating,
                missing=report.missing,
                source_topic=report.source_topic,
                assignments=assignments,
            )
        )
    return ok(result)


@router.get(
    "/performance",
    response_model=Envelope[list[PerformanceRow]],
    tags=["Reports"],
    summary="Performance roll-up",
    responses={**UNAUTHORIZED},
)
def get_performance(
    start: date = Query(alias="from", description="Inclusive start day (YYYY-MM-DD)."),
    end: date = Query(alias="to", description="Inclusive end day (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """Per-person performance over `[from, to]` — average rating, report completion rate (%),
    missing days, and assignment count — sorted best-first (a leaderboard)."""
    days = max(1, (end - start).days + 1)
    people = list(db.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.sort_order)))
    rows = []
    for person in people:
        reports = list(
            db.scalars(
                select(Report).where(
                    Report.person_id == person.id,
                    Report.report_date >= start,
                    Report.report_date <= end,
                )
            )
        )
        ratings = [report.rating for report in reports if report.rating is not None]
        missing_days = sum(1 for report in reports if report.missing)
        assignment_count = db.scalar(
            select(func.count(Assignment.id)).where(Assignment.person_id == person.id, Assignment.active.is_(True))
        ) or 0
        rows.append(
            PerformanceRow(
                person=person_out(person),
                average_rating=round(sum(ratings) / len(ratings), 2) if ratings else None,
                report_completion_rate=round((len([r for r in reports if not r.missing]) / days) * 100, 1),
                missing_days=missing_days,
                assignment_count=assignment_count,
            )
        )
    rows.sort(key=lambda item: (item.average_rating or 0, item.report_completion_rate), reverse=True)
    return ok(rows)


@router.get(
    "/goals",
    response_model=Envelope[list[GoalOut]],
    tags=["Goals"],
    summary="List goals",
    responses={**UNAUTHORIZED},
)
def get_goals(
    goal_status: str | None = Query(
        default=None, alias="status", description="Optional filter: active | overdue | done | paused."
    ),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
) -> Envelope:
    """All goals (status derived from deadline), each with owner, progress, deadline,
    next nudge, and the latest progress-log entry. Optionally filter by `status`."""
    goals = list(db.scalars(select(Goal).order_by(Goal.deadline.asc().nullslast(), Goal.updated_at.desc())))
    result = [goal_out(db, goal) for goal in goals]
    if goal_status:
        result = [goal for goal in result if goal.status == goal_status]
    return ok(result)


@router.get(
    "/project-conditions",
    response_model=Envelope[list[ProjectConditionOut]],
    tags=["Projects"],
    summary="Project conditions",
    responses={**UNAUTHORIZED},
)
def get_project_conditions(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> Envelope:
    """Current condition for each active project topic — rolling summary, last activity,
    and open items."""
    topics = list(db.scalars(select(ProjectTopic).where(ProjectTopic.active.is_(True)).order_by(ProjectTopic.topic_id)))
    result = []
    for topic in topics:
        condition = db.scalar(select(ProjectCondition).where(ProjectCondition.topic_id == topic.topic_id))
        result.append(project_condition_out(topic, condition))
    return ok(result)


@router.post(
    "/viper/attendance",
    response_model=Envelope[AttendanceOut],
    tags=["Viper ingest"],
    summary="Upsert attendance (Viper)",
    responses={**VIPER_UNAUTHORIZED},
)
def viper_attendance(
    payload: ViperAttendanceUpsert,
    db: Session = Depends(get_db),
    _: str = Depends(require_viper),
) -> Envelope:
    """Idempotent upsert of one person's attendance for a shift day (keyed on person + date).
    The person is created on first sight. Charge/late policy is computed server-side."""
    record = upsert_attendance(db, payload)
    db.commit()
    db.refresh(record)
    return ok(attendance_out(record))


@router.post(
    "/viper/report",
    response_model=Envelope[IdResult],
    tags=["Viper ingest"],
    summary="Upsert daily report (Viper)",
    responses={**VIPER_UNAUTHORIZED},
)
def viper_report(
    payload: ViperReportUpsert,
    db: Session = Depends(get_db),
    _: str = Depends(require_viper),
) -> Envelope:
    """Idempotent upsert of one person's daily report (keyed on person + date). Returns the report id."""
    report = upsert_report(db, payload)
    db.commit()
    db.refresh(report)
    return ok({"id": report.id})


@router.post(
    "/viper/goal",
    response_model=Envelope[GoalOut],
    tags=["Viper ingest"],
    summary="Upsert goal (Viper)",
    responses={**VIPER_UNAUTHORIZED},
)
def viper_goal(
    payload: ViperGoalUpsert,
    db: Session = Depends(get_db),
    _: str = Depends(require_viper),
) -> Envelope:
    """Idempotent upsert of a goal (keyed on `slug`). `progress_log`, if present, is appended
    as a timestamped log entry. Returns the resolved goal."""
    goal = upsert_goal(db, payload)
    db.commit()
    db.refresh(goal)
    return ok(goal_out(db, goal))


@router.post(
    "/viper/project-condition",
    response_model=Envelope[ProjectConditionOut],
    tags=["Viper ingest"],
    summary="Upsert project condition (Viper)",
    responses={**VIPER_UNAUTHORIZED},
)
def viper_project_condition(
    payload: ViperProjectConditionUpsert,
    db: Session = Depends(get_db),
    _: str = Depends(require_viper),
) -> Envelope:
    """Idempotent upsert of a topic's rolling condition (keyed on `topic_id`) — summary,
    last activity, and open items. Returns the resolved condition."""
    condition = upsert_project_condition(db, payload)
    db.commit()
    topic = db.get(ProjectTopic, condition.topic_id)
    return ok(project_condition_out(topic, condition))  # type: ignore[arg-type]


@router.post(
    "/sheets/sync/attendance",
    response_model=Envelope[SheetSyncResult],
    tags=["Google Sheets"],
    summary="Sync attendance to the sheet",
    responses={**UNAUTHORIZED},
)
def sheets_sync_attendance(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> Envelope:
    """Push current attendance to the configured HR sheet and return the sync run's status."""
    run = sync_attendance_to_sheet(db)
    db.commit()
    return ok(
        {
            "id": run.id,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error_message": run.error_message,
        }
    )


@router.get(
    "/google-sheet/preview",
    response_model=Envelope[GoogleSheetPreview],
    tags=["Google Sheets"],
    summary="Preview the HR sheet",
    responses={**UNAUTHORIZED, **SHEET_ERROR},
)
def google_sheet_preview(
    sample_rows: int = Query(default=8, ge=1, le=25, description="Rows to sample per tab (1–25)."),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> Envelope:
    """Spreadsheet title and, per tab, its dimensions, sample range, and a few sample rows —
    used to verify the Google Sheet wiring before importing."""
    try:
        preview: GoogleSheetPreview = get_sheet_preview(settings, sample_rows=sample_rows)
    except GoogleSheetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(preview)


@router.post(
    "/google-sheet/import",
    response_model=Envelope[GoogleSheetImportResult],
    tags=["Google Sheets"],
    summary="Import recognized tabs",
    responses={**UNAUTHORIZED, **SHEET_ERROR},
)
def google_sheet_import(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_admin),
) -> Envelope:
    """Import rows from tabs with recognizable canonical headers into the dashboard, returning
    counts of imported rows and any skipped tabs."""
    try:
        result: GoogleSheetImportResult = import_google_sheet_dashboard_data(settings, db)
    except GoogleSheetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ok(result)
