from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.bootstrap import seed_db
from backend.app.db import Base
from backend.app.models import AttendanceRecord
from backend.app.schemas import ViperAttendanceUpsert, ViperPersonRef
from backend.app.services import upsert_attendance

TZ = ZoneInfo("Asia/Tashkent")


def make_db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    session.commit()
    return session


def payload(day: date, minute: int) -> ViperAttendanceUpsert:
    return ViperAttendanceUpsert(
        person=ViperPersonRef(slug="abdul", display_name="Abdul"),
        shift_date=day,
        check_in_at=datetime(day.year, day.month, day.day, 18, minute, tzinfo=TZ),
    )


def test_on_time_arrival_is_on_time() -> None:
    db = make_db()
    record = upsert_attendance(db, payload(date(2026, 6, 1), 0))
    assert record.status == "on_time"
    assert record.minutes_late == 0


def test_within_grace_is_late() -> None:
    db = make_db()
    record = upsert_attendance(db, payload(date(2026, 6, 1), 10))
    assert record.status == "late"
    assert record.minutes_late == 10


def test_beyond_grace_is_late_15() -> None:
    db = make_db()
    record = upsert_attendance(db, payload(date(2026, 6, 1), 25))
    assert record.status == "late_15"
    assert record.minutes_late == 25


def test_no_check_in_is_no_show() -> None:
    db = make_db()
    record = upsert_attendance(
        db,
        ViperAttendanceUpsert(
            person=ViperPersonRef(slug="no-show", display_name="No Show"),
            shift_date=date(2026, 6, 1),
            check_in_at=None,
        ),
    )
    saved = db.get(AttendanceRecord, record.id)
    assert saved is not None
    assert saved.status == "no_show"


def test_explicit_absent() -> None:
    db = make_db()
    record = upsert_attendance(
        db,
        ViperAttendanceUpsert(
            person=ViperPersonRef(slug="abdul", display_name="Abdul"),
            shift_date=date(2026, 6, 1),
            check_in_at=datetime(2026, 6, 1, 18, 0, tzinfo=TZ),
            status="absent",
        ),
    )
    assert record.status == "absent"
