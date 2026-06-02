from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.bootstrap import seed_db
from backend.app.db import Base
from backend.app.models import AttendancePolicy, AttendanceRecord
from backend.app.schemas import ViperAttendanceUpsert, ViperPersonRef
from backend.app.services import upsert_attendance


def make_db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    policy = session.scalar(select(AttendancePolicy))
    assert policy is not None
    policy.charge_amount_uzs = 50_000
    session.commit()
    return session


def payload(day: date, minute: int) -> ViperAttendanceUpsert:
    tz = ZoneInfo("Asia/Tashkent")
    return ViperAttendanceUpsert(
        person=ViperPersonRef(slug="abdul", display_name="Abdul"),
        shift_date=day,
        check_in_at=datetime(day.year, day.month, day.day, 18, minute, tzinfo=tz),
    )


def test_first_grace_late_is_free_then_second_is_charged() -> None:
    db = make_db()
    first = upsert_attendance(db, payload(date(2026, 6, 1), 10))
    db.commit()
    second = upsert_attendance(db, payload(date(2026, 6, 2), 12))
    db.commit()

    assert first.status == "late"
    assert first.charged is False
    assert second.status == "charged"
    assert second.charge_reason == "second_late_week"
    assert second.charge_amount_uzs == 50_000


def test_late_after_grace_is_charged() -> None:
    db = make_db()
    record = upsert_attendance(db, payload(date(2026, 6, 1), 25))
    db.commit()

    assert record.status == "charged"
    assert record.minutes_late == 25
    assert record.charge_reason == "late_after_grace"


def test_no_show_is_charged() -> None:
    db = make_db()
    record = upsert_attendance(
        db,
        ViperAttendanceUpsert(
            person=ViperPersonRef(slug="no-show", display_name="No Show"),
            shift_date=date(2026, 6, 1),
            check_in_at=None,
        ),
    )
    db.commit()

    saved = db.get(AttendanceRecord, record.id)
    assert saved is not None
    assert saved.status == "no_show"
    assert saved.charged is True
    assert saved.charge_reason == "no_show"

