import json
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ratelimit
from .attendance_sheet import import_attendance_sheet
from .auth import (
    check_password,
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    require_edit,
    require_view,
    require_viper,
)
from .config import Settings, get_settings
from .db import get_db, utc_now
from .google_sheets import GoogleSheetError, get_sheet_preview, import_google_sheet_dashboard_data
from .permissions import permissions_for
from .models import (
    Assignment,
    AttendanceRecord,
    AuditLog,
    Evaluation,
    Feedback,
    Goal,
    GoalLog,
    Person,
    ProjectCondition,
    ProjectLog,
    ProjectTopic,
    Report,
    User,
)
from .schemas import (
    AttendanceCell,
    AttendanceHistoryRow,
    AttendanceOut,
    ChangePasswordRequest,
    ChasePatchRequest,
    DashboardOverview,
    Envelope,
    GoalOut,
    GoogleSheetImportResult,
    GoogleSheetPreview,
    EvaluationOut,
    FeedbackOut,
    IdResult,
    LoginRequest,
    LoginResponse,
    MeOut,
    PerformanceRow,
    PersonOut,
    ProjectConditionOut,
    ProjectCreate,
    ProjectDeleted,
    ProjectLogCreate,
    ProjectLogOut,
    ProjectUpdate,
    ReportOut,
    ResetPasswordRequest,
    SheetSyncResult,
    UserCreate,
    UserDeleted,
    UserOut,
    UserUpdate,
    ViperAttendanceUpsert,
    ViperEvaluationUpsert,
    ViperFeedbackUpsert,
    ViperGoalUpsert,
    ViperProjectConditionUpsert,
    ViperReportUpsert,
    WeeklySummaryRow,
)
from .services import (
    add_project_log,
    apply_goal_status,
    compute_performance_rows,
    create_feedback,
    create_project,
    date_span,
    delete_project,
    delete_project_log,
    get_project_logs,
    parse_project_tasks,
    sync_attendance_to_sheet,
    update_project,
    upsert_attendance,
    upsert_evaluation,
    upsert_goal,
    upsert_project_condition,
    upsert_report,
    week_bounds,
)

logger = logging.getLogger("sigma.routes")

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


def project_condition_out(
    topic: ProjectTopic,
    condition: ProjectCondition | None,
    logs: list[ProjectLog] | None = None,
) -> ProjectConditionOut:
    return ProjectConditionOut(
        topic_id=topic.topic_id,
        title=topic.title,
        summary=(condition.summary or None) if condition else None,
        last_activity_at=condition.last_activity_at if condition else None,
        open_items=parse_project_tasks(condition.open_items_json) if condition else [],
        logs=[ProjectLogOut(id=log.id, body=log.body, created_at=log.created_at) for log in (logs or [])],
        active=topic.active,
        updated_at=condition.updated_at if condition else None,
    )


def build_project_out(db: Session, topic: ProjectTopic) -> ProjectConditionOut:
    """Assemble the full project payload (condition + recent logs) for a single topic."""
    condition = db.scalar(select(ProjectCondition).where(ProjectCondition.topic_id == topic.topic_id))
    return project_condition_out(topic, condition, get_project_logs(db, topic.topic_id))


@router.post(
    "/auth/login",
    response_model=Envelope[LoginResponse],
    tags=["Auth"],
    summary="Log in as admin",
    responses={**UNAUTHORIZED},
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Envelope:
    """Exchange a username + password for a bearer JWT.

    Returns `data.access_token` (send it as `Authorization: Bearer <token>`), the
    account's `role`, and `must_change_password` (true when the password is a temp
    one that must be rotated before the rest of the API will respond).
    """
    client_key = request.client.host if request.client else "unknown"
    if not ratelimit.allow(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts — try again in a minute",
        )
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.active or not check_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    user.last_login_at = utc_now()
    db.commit()
    token, expires_at = create_access_token(settings, user.username, user.role)
    return ok(
        LoginResponse(
            access_token=token,
            expires_at=expires_at,
            username=user.username,
            display_name=user.display_name,
            role=user.role,  # type: ignore[arg-type]
            must_change_password=user.must_change_password,
        )
    )


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
    _: User = Depends(require_view),
) -> Envelope:
    """Aggregated home view for a shift day: tonight's attendance, the weekly lateness
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
    _: User = Depends(require_view),
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
    _: User = Depends(require_view),
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
                )
            )
        rows.append(AttendanceHistoryRow(person=person_out(person), cells=cells))
    return ok(rows)


@router.get(
    "/attendance/weekly-summary",
    response_model=Envelope[list[WeeklySummaryRow]],
    tags=["Attendance"],
    summary="Weekly attendance summary",
    responses={**UNAUTHORIZED},
)
def get_weekly_summary(
    week_start: date = Query(description="Monday of the target week (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: User = Depends(require_view),
) -> Envelope:
    """Per-person counts of each attendance status (on_time / late / late_15 / no_show /
    absent) for the Mon–Sun week beginning at `week_start`. `meta` echoes the resolved
    `week_start`/`week_end`."""
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
        counts = {status: 0 for status in ("on_time", "late", "late_15", "no_show", "absent")}
        for record in records:
            if record.status in counts:
                counts[record.status] += 1
        rows.append(
            WeeklySummaryRow(
                person=person_out(person),
                on_time=counts["on_time"],
                late=counts["late"],
                late_15=counts["late_15"],
                no_show=counts["no_show"],
                absent=counts["absent"],
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
    _: User = Depends(require_edit),
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
    _: User = Depends(require_view),
) -> Envelope:
    """Each person's report for the given day — summary, extras, rating (0–100), missing
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
    latest = db.scalar(
        select(func.max(Report.report_date)).where(Report.report_date <= report_date)
    )
    return ok(result, {"latest_report_date": latest.isoformat() if latest else None})


def evaluation_out(evaluation: Evaluation, person: Person) -> EvaluationOut:
    return EvaluationOut(
        id=evaluation.id,
        person=person_out(person),
        period_start=evaluation.period_start,
        period_end=evaluation.period_end,
        grade=evaluation.grade,
        what=evaluation.what,
        how=evaluation.how,
        why=evaluation.why,
        composite_score=evaluation.composite_score,
        updated_at=evaluation.updated_at,
    )


def feedback_out(item: Feedback, person: Person) -> FeedbackOut:
    return FeedbackOut(
        id=item.id,
        person=person_out(person),
        feedback_date=item.feedback_date,
        note=item.note,
        source=item.source,
        grade_adjustment=item.grade_adjustment,
        created_at=item.created_at,
    )


@router.get(
    "/performance",
    response_model=Envelope[list[PerformanceRow]],
    tags=["Performance"],
    summary="Performance leaderboard",
    responses={**UNAUTHORIZED},
)
def get_performance(
    start: date = Query(alias="from", description="Inclusive start day (YYYY-MM-DD)."),
    end: date = Query(alias="to", description="Inclusive end day (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: User = Depends(require_view),
) -> Envelope:
    """Per-person performance over `[from, to]`, best→worst: WHAT (avg rating + trend, completion %,
    accomplishment) + HOW (avg check-in/out, status counts, compensation, avg hours, punctuality) +
    the output-anchored **composite grade** (attendance penalises; latest feedback adjusts ±1 band).
    Completion % is over Mon–Sat work-days."""
    rows = [PerformanceRow(person=person_out(person), **metrics) for person, metrics in compute_performance_rows(db, start, end)]
    return ok(rows)


@router.post(
    "/viper/evaluation",
    response_model=Envelope[EvaluationOut],
    tags=["Viper ingest"],
    summary="Upsert weekly evaluation (Viper)",
    responses={**VIPER_UNAUTHORIZED},
)
def viper_evaluation(
    payload: ViperEvaluationUpsert,
    db: Session = Depends(get_db),
    _: str = Depends(require_viper),
) -> Envelope:
    """Idempotent upsert of a person's holistic WHAT/HOW/WHY evaluation for a period (keyed on
    person + period_start + period_end). Produced weekly by Viper's performance-evaluation skill."""
    evaluation = upsert_evaluation(db, payload)
    db.commit()
    person = db.get(Person, evaluation.person_id)
    return ok(evaluation_out(evaluation, person))  # type: ignore[arg-type]


@router.get(
    "/evaluations",
    response_model=Envelope[list[EvaluationOut]],
    tags=["Performance"],
    summary="Evaluations in a window",
    responses={**UNAUTHORIZED},
)
def get_evaluations(
    start: date = Query(alias="from", description="Inclusive start day (YYYY-MM-DD)."),
    end: date = Query(alias="to", description="Inclusive end day (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: User = Depends(require_view),
) -> Envelope:
    """Evaluations whose period overlaps `[from, to]`, newest period first (latest per person is the
    one the Performance tab shows under WHY)."""
    evaluations = list(
        db.scalars(
            select(Evaluation)
            .where(Evaluation.period_start <= end, Evaluation.period_end >= start)
            .order_by(Evaluation.period_start.desc(), Evaluation.id.desc())
        )
    )
    result = [evaluation_out(ev, db.get(Person, ev.person_id)) for ev in evaluations]  # type: ignore[arg-type]
    return ok(result)


@router.post(
    "/viper/feedback",
    response_model=Envelope[FeedbackOut],
    tags=["Viper ingest"],
    summary="Add feedback note (Viper)",
    responses={**VIPER_UNAUTHORIZED},
)
def viper_feedback(
    payload: ViperFeedbackUpsert,
    db: Session = Depends(get_db),
    _: str = Depends(require_viper),
) -> Envelope:
    """Append a feedback note for a person (Abdul's judgment, logged as spoken). `grade_adjustment`
    (-1/0/+1) lets the most recent feedback in a window nudge the composite grade by a band."""
    item = create_feedback(db, payload)
    db.commit()
    person = db.get(Person, item.person_id)
    return ok(feedback_out(item, person))  # type: ignore[arg-type]


@router.get(
    "/feedback",
    response_model=Envelope[list[FeedbackOut]],
    tags=["Performance"],
    summary="Feedback in a window",
    responses={**UNAUTHORIZED},
)
def get_feedback(
    start: date = Query(alias="from", description="Inclusive start day (YYYY-MM-DD)."),
    end: date = Query(alias="to", description="Inclusive end day (YYYY-MM-DD)."),
    db: Session = Depends(get_db),
    _: User = Depends(require_view),
) -> Envelope:
    """Feedback notes dated within `[from, to]`, newest first — the per-person timeline under WHY."""
    items = list(
        db.scalars(
            select(Feedback)
            .where(Feedback.feedback_date >= start, Feedback.feedback_date <= end)
            .order_by(Feedback.feedback_date.desc(), Feedback.id.desc())
        )
    )
    result = [feedback_out(item, db.get(Person, item.person_id)) for item in items]  # type: ignore[arg-type]
    return ok(result)


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
    _: User = Depends(require_view),
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
def get_project_conditions(
    db: Session = Depends(get_db),
    _: User = Depends(require_view),
    include_archived: bool = Query(default=False, description="Include archived (active=false) projects."),
) -> Envelope:
    """Condition for each project topic — rolling summary, last activity, the open task
    checklist, and the recent log timeline. Active projects only by default; pass
    `include_archived=true` to also return archived ones (so they can be restored)."""
    stmt = select(ProjectTopic).order_by(ProjectTopic.topic_id)
    if not include_archived:
        stmt = stmt.where(ProjectTopic.active.is_(True))
    return ok([build_project_out(db, topic) for topic in db.scalars(stmt)])


@router.post(
    "/projects",
    response_model=Envelope[ProjectConditionOut],
    tags=["Projects"],
    summary="Create a project",
    responses={**UNAUTHORIZED, 409: _err("A project with that topic_id already exists.")},
)
def create_project_endpoint(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_edit),
) -> Envelope:
    """Create a new project topic and its condition. `topic_id` is auto-generated when omitted."""
    try:
        topic = create_project(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    db.commit()
    return ok(build_project_out(db, topic))


@router.patch(
    "/projects/{topic_id}",
    response_model=Envelope[ProjectConditionOut],
    tags=["Projects"],
    summary="Update a project",
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def update_project_endpoint(
    topic_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_edit),
) -> Envelope:
    """Patch a project's title, summary, task checklist, or active (archive) flag. Omitted
    fields are left unchanged; archive sets `active=false` (hides it from the board)."""
    topic = update_project(db, topic_id, payload)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    db.commit()
    return ok(build_project_out(db, topic))


@router.delete(
    "/projects/{topic_id}",
    response_model=Envelope[ProjectDeleted],
    tags=["Projects"],
    summary="Delete a project",
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def delete_project_endpoint(
    topic_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_edit),
) -> Envelope:
    """Permanently remove a project, its condition, and its logs. Referencing goals are detached."""
    if not delete_project(db, topic_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    db.commit()
    return ok(ProjectDeleted(topic_id=topic_id))


@router.post(
    "/projects/{topic_id}/logs",
    response_model=Envelope[ProjectConditionOut],
    tags=["Projects"],
    summary="Add a project log entry",
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def add_project_log_endpoint(
    topic_id: str,
    payload: ProjectLogCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_edit),
) -> Envelope:
    """Append a timestamped log entry and bump the project's last activity. Returns the full project."""
    log = add_project_log(db, topic_id, payload.body)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    db.commit()
    topic = db.get(ProjectTopic, topic_id)
    return ok(build_project_out(db, topic))  # type: ignore[arg-type]


@router.delete(
    "/projects/{topic_id}/logs/{log_id}",
    response_model=Envelope[ProjectConditionOut],
    tags=["Projects"],
    summary="Delete a project log entry",
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def delete_project_log_endpoint(
    topic_id: str,
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_edit),
) -> Envelope:
    """Remove a single log entry from a project. Returns the full project."""
    if not delete_project_log(db, topic_id, log_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="log not found")
    db.commit()
    topic = db.get(ProjectTopic, topic_id)
    return ok(build_project_out(db, topic))  # type: ignore[arg-type]


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
    The person must already be in the roster (422 otherwise). The status is derived server-side."""
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
def sheets_sync_attendance(db: Session = Depends(get_db), _: User = Depends(require_edit)) -> Envelope:
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
    _: User = Depends(require_view),
) -> Envelope:
    """Spreadsheet title and, per tab, its dimensions, sample range, and a few sample rows —
    used to verify the Google Sheet wiring before importing."""
    try:
        preview: GoogleSheetPreview = get_sheet_preview(settings, sample_rows=sample_rows)
    except GoogleSheetError as exc:
        logger.warning("google sheet operation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Sheet operation failed — see server logs",
        ) from exc
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
    _: User = Depends(require_edit),
) -> Envelope:
    """Import rows from tabs with recognizable canonical headers into the dashboard, returning
    counts of imported rows and any skipped tabs."""
    try:
        result: GoogleSheetImportResult = import_google_sheet_dashboard_data(settings, db)
    except GoogleSheetError as exc:
        logger.warning("google sheet operation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Sheet operation failed — see server logs",
        ) from exc
    db.commit()
    return ok(result)


@router.post(
    "/attendance/import-sheet",
    response_model=Envelope[SheetSyncResult],
    tags=["Attendance"],
    summary="Import attendance from the HR sheet now",
    responses={**UNAUTHORIZED},
)
def import_attendance_sheet_now(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: User = Depends(require_edit),
) -> Envelope:
    """Pull the wide `Sigma Attendnace` tab into the dashboard immediately — the same job the
    daily 19:00 Asia/Tashkent auto-sync runs. Returns the recorded sync run (status + summary)."""
    run = import_attendance_sheet(settings, db)
    db.commit()
    return ok(
        SheetSyncResult(
            id=run.id,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error_message=run.error_message,
        )
    )


# --------------------------------------------------------------------------- #
# Accounts: current-user info, self password change, and admin user management
# --------------------------------------------------------------------------- #

ADMIN_ONLY = {403: _err("Admin access required.")}


def user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


def me_out(user: User) -> MeOut:
    return MeOut(
        username=user.username,
        display_name=user.display_name,
        role=user.role,  # type: ignore[arg-type]
        permissions=permissions_for(user.role),
        must_change_password=user.must_change_password,
    )


def _hash_or_422(password: str) -> str:
    try:
        return hash_password(password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _active_admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.role == "admin", User.active.is_(True))
    ) or 0


def _audit(db: Session, actor: str, action: str, resource: str, detail: dict | None = None) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            resource=resource,
            detail_json=json.dumps(detail or {}),
            created_at=utc_now(),
        )
    )


@router.get(
    "/auth/me",
    response_model=Envelope[MeOut],
    tags=["Auth"],
    summary="Current signed-in user",
    responses={**UNAUTHORIZED},
)
def auth_me(user: User = Depends(get_current_user)) -> Envelope:
    """The signed-in account plus its role permission map. Reachable even when a
    temp-password change is pending, so the frontend can show the change-password screen."""
    return ok(me_out(user))


@router.post(
    "/auth/change-password",
    response_model=Envelope[MeOut],
    tags=["Auth"],
    summary="Change your own password",
    responses={**UNAUTHORIZED, 400: _err("Current password is incorrect.")},
)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Envelope:
    """Set a new password for the signed-in account. Clears the temp-password flag,
    so after this call the rest of the API responds normally."""
    if not check_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = _hash_or_422(payload.new_password)
    user.must_change_password = False
    _audit(db, user.username, "change_password", f"user:{user.username}")
    db.commit()
    db.refresh(user)
    return ok(me_out(user))


@router.get(
    "/users",
    response_model=Envelope[list[UserOut]],
    tags=["Users"],
    summary="List users",
    responses={**UNAUTHORIZED, **ADMIN_ONLY},
)
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> Envelope:
    """All login accounts, ordered by username. Admin only."""
    users = list(db.scalars(select(User).order_by(User.username)))
    return ok([user_out(u) for u in users])


@router.post(
    "/users",
    response_model=Envelope[UserOut],
    tags=["Users"],
    summary="Create a user",
    responses={**UNAUTHORIZED, **ADMIN_ONLY, 409: _err("Username already exists.")},
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Envelope:
    """Create a login account with a temp password (defaults to forcing a change on first login)."""
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with that username already exists")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        role=payload.role,
        password_hash=_hash_or_422(payload.temp_password),
        active=True,
        must_change_password=payload.must_change_password,
    )
    db.add(user)
    _audit(db, admin.username, "create_user", f"user:{payload.username}", {"role": payload.role})
    db.commit()
    db.refresh(user)
    return ok(user_out(user))


@router.patch(
    "/users/{user_id}",
    response_model=Envelope[UserOut],
    tags=["Users"],
    summary="Update a user",
    responses={**UNAUTHORIZED, **ADMIN_ONLY, **NOT_FOUND, 409: _err("Would remove the last active admin.")},
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Envelope:
    """Change a user's display name, role, or active flag. Refuses to demote or disable
    the last active admin (so you can never lock everyone out)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    would_remove_admin = (payload.role is not None and payload.role != "admin") or payload.active is False
    if user.role == "admin" and user.active and would_remove_admin and _active_admin_count(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot demote or disable the last active admin",
        )
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        user.role = payload.role
    if payload.active is not None:
        user.active = payload.active
    _audit(db, admin.username, "update_user", f"user:{user.username}", payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(user)
    return ok(user_out(user))


@router.post(
    "/users/{user_id}/reset-password",
    response_model=Envelope[UserOut],
    tags=["Users"],
    summary="Reset a user's password",
    responses={**UNAUTHORIZED, **ADMIN_ONLY, **NOT_FOUND},
)
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Envelope:
    """Set a new temp password for a user (defaults to forcing a change on next login)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    user.password_hash = _hash_or_422(payload.temp_password)
    user.must_change_password = payload.must_change_password
    _audit(db, admin.username, "reset_password", f"user:{user.username}")
    db.commit()
    db.refresh(user)
    return ok(user_out(user))


@router.delete(
    "/users/{user_id}",
    response_model=Envelope[UserDeleted],
    tags=["Users"],
    summary="Delete a user",
    responses={**UNAUTHORIZED, **ADMIN_ONLY, **NOT_FOUND, 400: _err("Cannot delete yourself or the last admin.")},
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Envelope:
    """Permanently delete a user. You cannot delete yourself or the last active admin —
    disable those instead (PATCH active=false)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
    if user.role == "admin" and user.active and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the last active admin")
    db.delete(user)
    _audit(db, admin.username, "delete_user", f"user:{user.username}")
    db.commit()
    return ok(UserDeleted(id=user_id))
