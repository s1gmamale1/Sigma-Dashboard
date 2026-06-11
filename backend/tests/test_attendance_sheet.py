from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.attendance_sheet import apply_attendance_rows, parse_attendance_grid
from backend.app.bootstrap import seed_db
from backend.app.db import Base
from backend.app.models import AttendanceRecord, Person

TZ = ZoneInfo("Asia/Tashkent")

# Wide HR layout: A=Date; Oliver B/C/D, Sam E/F/G (Arrival/Out/Status); names on row 2, data from row 4.
GRID = [
    ["Name"],
    ["", "Oliver", "", "", "Sam", "", ""],
    ["Date", "Arrival time", "Out time", "Status", "Arrival time", "Out time", "Status"],
    ["2026-06-01", "18:00", "", "On time", "", "", "No Show"],
    ["2026-06-02", "18:25", "", "15+ Late", "", "", "Absent"],
]


def make_db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    session.commit()
    return session


def test_parse_wide_grid() -> None:
    rows = parse_attendance_grid(GRID)
    # 2 people x 2 days, but only cells with data: Oliver has both days; Sam has status both days.
    keyed = {(r.slug, r.shift_date): r for r in rows}
    assert keyed[("oliver", date(2026, 6, 1))].arrival == "18:00"
    assert keyed[("oliver", date(2026, 6, 1))].status_text == "On time"
    assert keyed[("sam", date(2026, 6, 1))].status_text == "No Show"
    assert keyed[("sam", date(2026, 6, 2))].status_text == "Absent"
    # rows are sorted chronologically
    assert [r.shift_date for r in rows] == sorted(r.shift_date for r in rows)


def test_apply_classifies_from_arrival_and_status() -> None:
    db = make_db()
    applied = apply_attendance_rows(db, parse_attendance_grid(GRID), TZ)
    db.commit()
    assert applied == 4

    by = {
        (db.get(Person, r.person_id).slug, r.shift_date): r
        for r in db.scalars(select(AttendanceRecord))
    }
    oliver_d1 = by[("oliver", date(2026, 6, 1))]
    assert oliver_d1.status == "on_time"

    oliver_d2 = by[("oliver", date(2026, 6, 2))]
    assert oliver_d2.status == "late_15" and oliver_d2.minutes_late == 25

    sam_d1 = by[("sam", date(2026, 6, 1))]
    assert sam_d1.status == "no_show"

    sam_d2 = by[("sam", date(2026, 6, 2))]
    assert sam_d2.status == "absent"


def test_resync_preserves_admin_chase_state() -> None:
    db = make_db()
    apply_attendance_rows(db, parse_attendance_grid(GRID), TZ)
    db.commit()

    record = db.scalar(
        select(AttendanceRecord).join(Person).where(Person.slug == "sam", AttendanceRecord.shift_date == date(2026, 6, 1))
    )
    record.chase_state = "chased"
    db.commit()

    # A second sync (e.g. the next 19:00 run) must not wipe the admin's chase progress.
    apply_attendance_rows(db, parse_attendance_grid(GRID), TZ)
    db.commit()
    db.refresh(record)
    assert record.chase_state == "chased"


def test_explicit_off_day_status() -> None:
    from backend.app.services import calculate_attendance_status

    db = make_db()
    assert calculate_attendance_status(db, date(2026, 6, 7), None, "off_day") == ("off_day", 0)


def test_off_day_record_satisfies_check_constraint() -> None:
    from backend.app.services import get_or_create_person

    db = make_db()
    person = get_or_create_person(db, "oliver", "Oliver")
    db.add(
        AttendanceRecord(
            person_id=person.id, shift_date=date(2026, 6, 7), status="off_day", chase_state="none"
        )
    )
    db.commit()  # would raise IntegrityError if off_day is not in the CHECK constraint
