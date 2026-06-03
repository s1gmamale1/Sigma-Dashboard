import json
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
    ProjectTopic,
    Report,
    SheetSyncRun,
)
from .schemas import ViperAttendanceUpsert, ViperGoalUpsert, ViperProjectConditionUpsert, ViperReportUpsert


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
    condition.open_items_json = json.dumps(payload.open_items)
    db.flush()
    return condition


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
