import json
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utc_now
from .models import (
    Assignment,
    AttendancePolicy,
    AttendanceRecord,
    Goal,
    GoalLog,
    Person,
    ProjectCondition,
    ProjectLog,
    ProjectTopic,
    Report,
    SheetSyncRun,
)
from .schemas import (
    ProjectCreate,
    ProjectUpdate,
    ViperAttendanceUpsert,
    ViperGoalUpsert,
    ViperProjectConditionUpsert,
    ViperReportUpsert,
)


def get_or_create_person(db: Session, slug: str, display_name: str) -> Person:
    person = db.scalar(select(Person).where(Person.slug == slug))
    if person is None:
        max_sort = db.scalar(select(func.max(Person.sort_order))) or 0
        person = Person(slug=slug, display_name=display_name, active=True, sort_order=max_sort + 1)
        db.add(person)
        db.flush()
    elif person.display_name != display_name:
        person.display_name = display_name
    return person


def get_active_policy(db: Session) -> AttendancePolicy:
    policy = db.scalar(select(AttendancePolicy).order_by(AttendancePolicy.id.asc()).limit(1))
    if policy is None:
        policy = AttendancePolicy(charge_amount_uzs=0)
        db.add(policy)
        db.flush()
    return policy


def week_bounds(shift_date: date) -> tuple[date, date]:
    start = shift_date - timedelta(days=shift_date.weekday())
    return start, start + timedelta(days=6)


def shift_start_datetime(shift_date: date, policy: AttendancePolicy) -> datetime:
    settings = get_settings()
    hour, minute = [int(part) for part in policy.shift_start_local.split(":")]
    return datetime.combine(shift_date, time(hour=hour, minute=minute), tzinfo=ZoneInfo(settings.timezone))


def calculate_attendance_status(
    db: Session,
    shift_date: date,
    check_in_at: datetime | None,
    explicit_status: str | None,
) -> tuple[str, int]:
    """Derive (status, minutes_late) from the arrival time. No charge concept.

    on_time (0 late) · late (1..grace) · late_15 (> grace) · no_show (no check-in) ·
    absent (explicit). The 15-minute grace splits `late` from `late_15`.
    """
    if explicit_status in {"absent", "excused"}:
        return "absent", 0
    if check_in_at is None:
        return "no_show", 0
    policy = get_active_policy(db)
    start_at = shift_start_datetime(shift_date, policy)
    minutes_late = max(0, int((check_in_at - start_at).total_seconds() // 60))
    if minutes_late == 0:
        return "on_time", 0
    if minutes_late <= policy.grace_minutes:
        return "late", minutes_late
    return "late_15", minutes_late


def upsert_attendance(db: Session, payload: ViperAttendanceUpsert) -> AttendanceRecord:
    person = get_or_create_person(db, payload.person.slug, payload.person.display_name)
    status, minutes_late = calculate_attendance_status(
        db, payload.shift_date, payload.check_in_at, payload.status
    )
    record = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.person_id == person.id,
            AttendanceRecord.shift_date == payload.shift_date,
        )
    )
    if record is None:
        record = AttendanceRecord(person_id=person.id, shift_date=payload.shift_date, status=status)
        db.add(record)
    record.check_in_at = payload.check_in_at
    record.check_out_at = payload.check_out_at
    record.status = status
    record.minutes_late = minutes_late
    record.chase_state = payload.chase_state
    record.notes = payload.notes
    db.flush()
    return record


def upsert_report(db: Session, payload: ViperReportUpsert) -> Report:
    person = get_or_create_person(db, payload.person.slug, payload.person.display_name)
    report = db.scalar(
        select(Report).where(Report.person_id == person.id, Report.report_date == payload.report_date)
    )
    if report is None:
        report = Report(person_id=person.id, report_date=payload.report_date, summary=payload.summary)
        db.add(report)
    report.summary = payload.summary
    report.extras = payload.extras
    report.rating = payload.rating
    report.missing = payload.missing
    report.source_topic = payload.source_topic
    db.flush()
    return report


def upsert_goal(db: Session, payload: ViperGoalUpsert) -> Goal:
    owner_id = None
    if payload.owner_slug:
        person = db.scalar(select(Person).where(Person.slug == payload.owner_slug))
        owner_id = person.id if person else None
    goal = db.scalar(select(Goal).where(Goal.slug == payload.slug))
    if goal is None:
        goal = Goal(slug=payload.slug, title=payload.title)
        db.add(goal)
    goal.title = payload.title
    goal.owner_person_id = owner_id
    goal.topic_id = payload.topic_id
    goal.deadline = payload.deadline
    goal.status = payload.status
    goal.progress_percent = payload.progress_percent
    goal.last_update_at = payload.last_update_at
    goal.next_nudge_at = payload.next_nudge_at
    db.flush()
    if payload.progress_log:
        db.add(GoalLog(goal_id=goal.id, body=payload.progress_log))
    db.flush()
    return goal


def parse_project_tasks(raw: str | None) -> list[dict]:
    """Read the stored open_items JSON into [{text, done}]. Legacy rows store plain
    strings (["a", "b"]); those are coerced to open tasks ({text, done: false})."""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    tasks: list[dict] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
            if text:
                tasks.append({"text": text, "done": False})
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            if text:
                tasks.append({"text": text, "done": bool(item.get("done", False))})
    return tasks


def _dump_tasks(tasks) -> str:
    """Serialize a list of ProjectTask (or dicts) to the stored JSON shape."""
    out = []
    for task in tasks:
        text = (task.text if hasattr(task, "text") else str(task.get("text", ""))).strip()
        if not text:
            continue
        done = bool(task.done if hasattr(task, "done") else task.get("done", False))
        out.append({"text": text, "done": done})
    return json.dumps(out)


def _generate_topic_id(db: Session) -> str:
    """A short, unique topic id for admin-created projects."""
    for _ in range(10):
        candidate = uuid.uuid4().hex[:10]
        if db.get(ProjectTopic, candidate) is None:
            return candidate
    return uuid.uuid4().hex


def upsert_project_condition(db: Session, payload: ViperProjectConditionUpsert) -> ProjectCondition:
    topic = db.get(ProjectTopic, payload.topic_id)
    if topic is None:
        topic = ProjectTopic(topic_id=payload.topic_id, title=f"LMS Topic {payload.topic_id}", active=True)
        db.add(topic)
        db.flush()
    condition = db.scalar(select(ProjectCondition).where(ProjectCondition.topic_id == payload.topic_id))
    if condition is None:
        condition = ProjectCondition(topic_id=payload.topic_id, summary=payload.summary)
        db.add(condition)
    condition.summary = payload.summary
    condition.last_activity_at = payload.last_activity_at
    # The agent sends plain strings; persist them as open tasks.
    condition.open_items_json = _dump_tasks([{"text": text, "done": False} for text in payload.open_items])
    db.flush()
    return condition


def get_project_logs(db: Session, topic_id: str, limit: int = 50) -> list[ProjectLog]:
    return list(
        db.scalars(
            select(ProjectLog)
            .where(ProjectLog.topic_id == topic_id)
            .order_by(ProjectLog.created_at.desc(), ProjectLog.id.desc())
            .limit(limit)
        )
    )


def create_project(db: Session, payload: ProjectCreate) -> ProjectTopic:
    """Admin: create a project topic + its condition. Raises ValueError on id collision."""
    topic_id = (payload.topic_id or "").strip() or _generate_topic_id(db)
    if db.get(ProjectTopic, topic_id) is not None:
        raise ValueError(f"topic_id '{topic_id}' already exists")
    topic = ProjectTopic(topic_id=topic_id, title=payload.title.strip(), active=True)
    db.add(topic)
    db.add(
        ProjectCondition(
            topic_id=topic_id,
            summary=(payload.summary or "").strip(),
            last_activity_at=None,
            open_items_json=_dump_tasks(payload.open_items),
        )
    )
    db.flush()
    return topic


def _ensure_condition(db: Session, topic_id: str) -> ProjectCondition:
    condition = db.scalar(select(ProjectCondition).where(ProjectCondition.topic_id == topic_id))
    if condition is None:
        condition = ProjectCondition(topic_id=topic_id, summary="", open_items_json="[]")
        db.add(condition)
    return condition


def update_project(db: Session, topic_id: str, payload: ProjectUpdate) -> ProjectTopic | None:
    """Admin: patch title/summary/tasks/active. Returns None if the topic is unknown."""
    topic = db.get(ProjectTopic, topic_id)
    if topic is None:
        return None
    if payload.title is not None:
        topic.title = payload.title.strip()
    if payload.active is not None:
        topic.active = payload.active
    if payload.summary is not None or payload.open_items is not None:
        condition = _ensure_condition(db, topic_id)
        if payload.summary is not None:
            condition.summary = payload.summary.strip()
        if payload.open_items is not None:
            condition.open_items_json = _dump_tasks(payload.open_items)
    db.flush()
    return topic


def add_project_log(db: Session, topic_id: str, body: str) -> ProjectLog | None:
    """Admin: append a log entry and bump the project's last activity. None if unknown topic."""
    topic = db.get(ProjectTopic, topic_id)
    if topic is None:
        return None
    log = ProjectLog(topic_id=topic_id, body=body.strip())
    db.add(log)
    _ensure_condition(db, topic_id).last_activity_at = utc_now()
    db.flush()
    return log


def delete_project_log(db: Session, topic_id: str, log_id: int) -> bool:
    log = db.get(ProjectLog, log_id)
    if log is None or log.topic_id != topic_id:
        return False
    db.delete(log)
    db.flush()
    return True


def delete_project(db: Session, topic_id: str) -> bool:
    """Admin: permanently remove a project and its dependents. None of the FK children
    may dangle, so logs/condition are removed first and referencing goals are detached."""
    topic = db.get(ProjectTopic, topic_id)
    if topic is None:
        return False
    for log in db.scalars(select(ProjectLog).where(ProjectLog.topic_id == topic_id)):
        db.delete(log)
    condition = db.scalar(select(ProjectCondition).where(ProjectCondition.topic_id == topic_id))
    if condition is not None:
        db.delete(condition)
    for goal in db.scalars(select(Goal).where(Goal.topic_id == topic_id)):
        goal.topic_id = None
    db.delete(topic)
    db.flush()
    return True


def attendance_range(db: Session, start: date, end: date) -> list[AttendanceRecord]:
    return list(
        db.scalars(
            select(AttendanceRecord)
            .where(AttendanceRecord.shift_date >= start, AttendanceRecord.shift_date <= end)
            .join(Person)
            .order_by(Person.sort_order, AttendanceRecord.shift_date)
        )
    )


def sync_attendance_to_sheet(db: Session) -> SheetSyncRun:
    started = utc_now()
    settings = get_settings()
    try:
        if not settings.google_credentials_path or not settings.google_sheet_id:
            raise RuntimeError("Google Sheets is not configured")
        rows = list(
            db.scalars(
                select(AttendanceRecord)
                .join(Person)
                .order_by(AttendanceRecord.shift_date.asc(), Person.sort_order.asc())
            )
        )
        values = [
            [
                "shift_date",
                "person",
                "status",
                "check_in_at",
                "check_out_at",
                "minutes_late",
                "chase_state",
                "notes",
            ]
        ]
        for record in rows:
            values.append(
                [
                    record.shift_date.isoformat(),
                    record.person.display_name,
                    record.status,
                    record.check_in_at.isoformat() if record.check_in_at else "",
                    record.check_out_at.isoformat() if record.check_out_at else "",
                    record.minutes_late,
                    record.chase_state,
                    record.notes or "",
                ]
            )
        credentials = Credentials.from_service_account_file(
            settings.google_credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        service.spreadsheets().values().update(
            spreadsheetId=settings.google_sheet_id,
            range="Attendance!A1",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()
        finished = utc_now()
        run = SheetSyncRun(
            sync_type="attendance",
            status="success",
            started_at=started,
            finished_at=finished,
            error_message=None,
        )
    except Exception as exc:
        finished = utc_now()
        run = SheetSyncRun(
            sync_type="attendance",
            status="failed",
            started_at=started,
            finished_at=finished,
            error_message=str(exc),
        )
    db.add(run)
    db.flush()
    return run


def date_span(start: date, end: date) -> list[date]:
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def apply_goal_status(goal: Goal) -> str:
    if goal.status == "done":
        return "done"
    if goal.deadline and goal.deadline < date.today():
        return "overdue"
    return goal.status
