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


def test_off_day_cell_creates_off_day_record() -> None:
    db = make_db()
    grid = [row[:] for row in GRID]
    grid.append(["2026-06-03", "OFF DAY", "", "", "18:00", "", "On time"])  # Oliver declared off
    apply_attendance_rows(db, parse_attendance_grid(grid), TZ)
    db.commit()

    record = db.scalar(
        select(AttendanceRecord)
        .join(Person)
        .where(Person.slug == "oliver", AttendanceRecord.shift_date == date(2026, 6, 3))
    )
    assert record is not None
    assert record.status == "off_day"
    assert record.check_in_at is None and record.check_out_at is None
    assert record.minutes_late == 0


def test_off_day_overwrites_stale_no_show() -> None:
    """P0 regression: a no_show imported earlier must be replaced when the same
    (person, date) cell is later declared OFF DAY — not silently kept."""
    db = make_db()
    apply_attendance_rows(db, parse_attendance_grid(GRID), TZ)
    db.commit()
    # Sam 2026-06-01 imported as no_show (from GRID). Admin had chased it.
    record = db.scalar(
        select(AttendanceRecord)
        .join(Person)
        .where(Person.slug == "sam", AttendanceRecord.shift_date == date(2026, 6, 1))
    )
    assert record.status == "no_show"
    record.chase_state = "chased"
    db.commit()

    resync = [row[:] for row in GRID]
    resync[3] = ["2026-06-01", "18:00", "", "On time", "OFF DAY", "", ""]  # Sam's day declared OFF
    apply_attendance_rows(db, parse_attendance_grid(resync), TZ)
    db.commit()

    db.refresh(record)
    assert record.status == "off_day"
    assert record.check_in_at is None
    assert record.chase_state == "chased"  # admin-owned fields preserved


def test_whole_team_sunday_off_day_row() -> None:
    """Viper writes 'OFF DAY' into col B and clears the rest of the row for a
    team-wide Sunday off. Every person must get an off_day record."""
    db = make_db()
    grid = [row[:] for row in GRID]
    grid.append(["2026-06-07", "OFF DAY", "", "", "", "", ""])
    rows = parse_attendance_grid(grid)

    sunday_rows = [r for r in rows if r.shift_date == date(2026, 6, 7)]
    assert sorted(r.slug for r in sunday_rows) == ["oliver", "sam"]

    apply_attendance_rows(db, rows, TZ)
    db.commit()
    statuses = {
        db.get(Person, r.person_id).slug: r.status
        for r in db.scalars(select(AttendanceRecord).where(AttendanceRecord.shift_date == date(2026, 6, 7)))
    }
    assert statuses == {"oliver": "off_day", "sam": "off_day"}


def test_off_day_excluded_from_performance_metrics() -> None:
    from backend.app.services import compute_performance_rows, get_or_create_person

    db = make_db()
    person = get_or_create_person(db, "oliver", "Oliver")
    db.add(
        AttendanceRecord(
            person_id=person.id, shift_date=date(2026, 6, 1), status="on_time", chase_state="none"
        )
    )
    db.add(
        AttendanceRecord(
            person_id=person.id, shift_date=date(2026, 6, 7), status="off_day", chase_state="none"
        )
    )
    db.commit()

    rows = compute_performance_rows(db, date(2026, 6, 1), date(2026, 6, 7))
    metrics = next(m for p, m in rows if p.slug == "oliver")
    assert metrics["punctuality_rate"] == 100.0  # off_day must not dilute the denominator
    assert metrics["attendance_days"] == 1       # off_day is not an attendance day


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


# --------------------------------------------------------------------------- #
# Auto-sync loop: imports on a short interval (not once/day), and never dies on error
# --------------------------------------------------------------------------- #

class _StopLoop(Exception):
    """Sentinel raised from the patched sleep to break the otherwise-infinite loop."""


def _drive_sync_loop(monkeypatch, interval_minutes: int, import_fn):
    """Run one iteration of main._attendance_sync_loop and capture the import/sleep calls."""
    import asyncio

    import pytest

    from backend.app import config, main

    sleeps: list[float] = []

    settings = config.Settings(
        jwt_secret="unit-test-jwt-secret-0123456789",
        viper_token="unit-test-viper-token-0123456789",
        sheet_sync_interval_minutes=interval_minutes,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "_run_attendance_import_once", import_fn)

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        raise _StopLoop

    monkeypatch.setattr(main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        asyncio.run(main._attendance_sync_loop())
    return sleeps


def test_sync_loop_imports_immediately_then_sleeps_the_interval(monkeypatch) -> None:
    calls = {"n": 0}

    def import_once() -> str:
        calls["n"] += 1
        return "success"

    sleeps = _drive_sync_loop(monkeypatch, interval_minutes=10, import_fn=import_once)

    assert calls["n"] == 1          # imported right away, not waiting until 19:00
    assert sleeps == [600.0]        # success → no backoff, sleeps the 10-minute interval


def test_sync_loop_survives_and_backs_off_on_raised_failure(monkeypatch) -> None:
    calls = {"n": 0}

    def import_boom() -> str:
        calls["n"] += 1
        raise RuntimeError("sheet unavailable")

    sleeps = _drive_sync_loop(monkeypatch, interval_minutes=5, import_fn=import_boom)

    assert calls["n"] == 1          # the failing import ran (loop survived the exception)
    assert sleeps == [600.0]        # 1 failure → 2x backoff over the 5-minute interval


def test_sync_loop_backs_off_on_failed_status(monkeypatch) -> None:
    calls = {"n": 0}

    def import_failed() -> str:
        calls["n"] += 1
        return "failed"             # import_attendance_sheet records failure, doesn't raise

    sleeps = _drive_sync_loop(monkeypatch, interval_minutes=10, import_fn=import_failed)

    assert calls["n"] == 1
    assert sleeps == [1200.0]       # a "failed" status also triggers the 2x backoff


def test_sync_interval_default_is_ten_minutes() -> None:
    from backend.app.config import Settings

    settings = Settings(
        jwt_secret="unit-test-jwt-secret-0123456789",
        viper_token="unit-test-viper-token-0123456789",
    )
    assert settings.sheet_sync_interval_minutes == 10


# --------------------------------------------------------------------------- #
# Import is serialized (lock) and the Sheets credentials are cached
# --------------------------------------------------------------------------- #

def test_import_attendance_sheet_runs_under_the_import_lock(monkeypatch) -> None:
    """The import body executes while _import_lock is held, so the interval loop and the
    on-demand endpoint can never run a sheet import concurrently."""
    from backend.app import attendance_sheet as A
    from backend.app.config import Settings

    held = {"locked": None}

    def probe_service(settings, api, version):
        held["locked"] = A._import_lock.locked()
        raise A.GoogleSheetError("stop after lock check")

    monkeypatch.setattr(A, "_service", probe_service)
    settings = Settings(
        jwt_secret="unit-test-jwt-secret-0123456789",
        viper_token="unit-test-viper-token-0123456789",
        google_credentials_path="/tmp/does-not-matter.json",
        google_sheet_id="sheet-123",  # set so resolve_spreadsheet_id returns without a _service call
    )
    run = A.import_attendance_sheet(settings, make_db())

    assert held["locked"] is True          # the body ran while the lock was held
    assert run.status == "failed"          # probe short-circuited; failure recorded, never raised
    assert not A._import_lock.locked()     # lock released after the call returns


def test_credentials_are_cached_per_path(monkeypatch) -> None:
    """The service-account file is read+parsed once per path, not on every import."""
    from backend.app import google_sheets as G
    from backend.app.config import Settings

    calls = {"n": 0}

    def fake_from_file(path, scopes=None):
        calls["n"] += 1
        return object()

    monkeypatch.setattr(G.Credentials, "from_service_account_file", fake_from_file)
    G._load_credentials.cache_clear()
    try:
        settings = Settings(
            jwt_secret="unit-test-jwt-secret-0123456789",
            viper_token="unit-test-viper-token-0123456789",
            google_credentials_path="/tmp/sa.json",
        )
        G._credentials(settings)
        G._credentials(settings)
        assert calls["n"] == 1             # parsed once; second call served from the cache
    finally:
        G._load_credentials.cache_clear()
