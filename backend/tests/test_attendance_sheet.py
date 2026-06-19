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


def _drive_sync_loop(monkeypatch, interval_minutes: int, import_fn, stop_after: int = 1):
    """Drive main._attendance_sync_loop for `stop_after` iterations, capturing each sleep."""
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
        if len(sleeps) >= stop_after:
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


def test_sync_loop_survives_single_failure_at_base_interval(monkeypatch) -> None:
    calls = {"n": 0}

    def import_boom() -> str:
        calls["n"] += 1
        raise RuntimeError("sheet unavailable")

    sleeps = _drive_sync_loop(monkeypatch, interval_minutes=5, import_fn=import_boom)

    assert calls["n"] == 1          # the import actually ran on the failure path
    # A single transient failure must NOT back off — the loop survives and retries at the
    # base interval (the regression the reviewer flagged: one blip shouldn't stretch staleness).
    assert sleeps == [300.0]


def test_sync_loop_escalates_then_resets_backoff(monkeypatch) -> None:
    statuses = iter(["failed", "failed", "failed", "success", "failed"])

    def import_seq() -> str:
        return next(statuses)

    sleeps = _drive_sync_loop(monkeypatch, interval_minutes=10, import_fn=import_seq, stop_after=5)

    # consecutive failures 1,2,3 → 1x,2x,4x; success resets → 1x; next failure → 1x again
    assert sleeps == [600.0, 1200.0, 2400.0, 600.0, 600.0]


def test_sync_loop_backoff_caps_at_8x(monkeypatch) -> None:
    def always_failed() -> str:
        return "failed"

    sleeps = _drive_sync_loop(monkeypatch, interval_minutes=10, import_fn=always_failed, stop_after=6)

    # 1,2,4,8 then capped at 8x — a long outage never stretches beyond 8x the interval
    assert sleeps == [600.0, 1200.0, 2400.0, 4800.0, 4800.0, 4800.0]


def test_sync_interval_default_is_ten_minutes() -> None:
    from backend.app.config import Settings

    settings = Settings(
        jwt_secret="unit-test-jwt-secret-0123456789",
        viper_token="unit-test-viper-token-0123456789",
    )
    assert settings.sheet_sync_interval_minutes == 10


# --------------------------------------------------------------------------- #
# Import is serialized: the DB apply runs under _import_lock, and concurrent
# imports never overlap (the fetch is outside the lock).
# --------------------------------------------------------------------------- #

def _sheets_settings():
    from backend.app.config import Settings

    return Settings(
        jwt_secret="unit-test-jwt-secret-0123456789",
        viper_token="unit-test-viper-token-0123456789",
    )


def test_import_fetches_outside_lock_applies_inside_and_persists_run(monkeypatch) -> None:
    """The fetch runs OUTSIDE _import_lock (no network I/O under the lock), the apply runs
    INSIDE it, and the SheetSyncRun is actually committed (not just held in memory)."""
    from backend.app import attendance_sheet as A
    from backend.app.models import SheetSyncRun

    observed = {"fetch_locked": None, "apply_locked": None}
    real_apply = A.apply_attendance_rows

    def probe_fetch(settings):
        observed["fetch_locked"] = A._import_lock.locked()
        return []

    def probe_apply(db, rows, tz):
        observed["apply_locked"] = A._import_lock.locked()
        return real_apply(db, rows, tz)

    monkeypatch.setattr(A, "_fetch_attendance_rows", probe_fetch)
    monkeypatch.setattr(A, "apply_attendance_rows", probe_apply)
    db = make_db()  # keep the session alive so run's attributes resolve after the internal commit
    run = A.import_attendance_sheet(_sheets_settings(), db)

    assert observed["fetch_locked"] is False   # fetch ran outside the lock (no starvation risk)
    assert observed["apply_locked"] is True     # apply ran inside the lock
    assert run.status == "success"
    assert run.id is not None                   # the run was actually committed...
    assert db.scalar(select(SheetSyncRun).where(SheetSyncRun.id == run.id)) is not None  # ...and persisted
    assert not A._import_lock.locked()          # released after the call returns


def test_import_serializes_concurrent_applies(monkeypatch) -> None:
    """Two overlapping imports never apply at the same time — the lock actually mutexes."""
    import threading
    import time

    from backend.app import attendance_sheet as A

    monkeypatch.setattr(A, "_fetch_attendance_rows", lambda settings: [])  # fetch is outside the lock
    overlap = {"max": 0, "cur": 0}
    counter = threading.Lock()

    def slow_apply(db, rows, tz):
        with counter:
            overlap["cur"] += 1
            overlap["max"] = max(overlap["max"], overlap["cur"])
        time.sleep(0.05)  # widen the window so a missing mutex would overlap
        with counter:
            overlap["cur"] -= 1
        return 0

    monkeypatch.setattr(A, "apply_attendance_rows", slow_apply)
    settings = _sheets_settings()
    errors: list[Exception] = []

    def worker():
        db = make_db()
        try:
            A.import_attendance_sheet(settings, db)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    assert all(not t.is_alive() for t in threads)  # no deadlock/hang (a lock bug would hang here)
    assert errors == []
    assert overlap["max"] == 1             # never two applies in flight → the lock serialized them


def test_import_serializes_real_upserts_on_shared_db(monkeypatch, tmp_path) -> None:
    """End-to-end: two concurrent imports of the SAME (person, shift_date) against ONE shared
    DB don't collide on the unique constraint — the lock serializes the real upsert + commit."""
    import threading

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app import attendance_sheet as A
    from backend.app.models import AttendanceRecord, Person

    engine = create_engine(
        f"sqlite:///{tmp_path / 'shared.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    seed = SessionFactory()
    seed_db(seed)
    seed.add(Person(slug="abdul", display_name="Abdul", active=True, sort_order=1))
    seed.commit()
    seed.close()

    # Both imports parse to the SAME (abdul, 2026-06-01) row, so they contend on uq_attendance_person_shift.
    grid = [
        ["Name"],
        ["", "Abdul", "", ""],
        ["Date", "Arrival time", "Out time", "Status"],
        ["2026-06-01", "18:00", "", "On time"],
    ]
    monkeypatch.setattr(A, "_fetch_attendance_rows", lambda settings: parse_attendance_grid(grid))
    settings = _sheets_settings()
    errors: list[Exception] = []

    def worker():
        db = SessionFactory()
        try:
            run = A.import_attendance_sheet(settings, db)
            if run.status != "success":
                errors.append(RuntimeError(run.error_message))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    assert all(not t.is_alive() for t in threads)
    assert errors == []                    # no IntegrityError / "database is locked" from the race
    check = SessionFactory()
    try:
        rows = check.scalars(select(AttendanceRecord).where(AttendanceRecord.shift_date == date(2026, 6, 1))).all()
    finally:
        check.close()
    assert len(rows) == 1                  # the unique row was upserted once, never duplicated
