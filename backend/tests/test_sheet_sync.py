"""Tests for the outbound dashboard→sheet push (services.sync_attendance_to_sheet).

The Google client is faked at the `services.Credentials`/`services.build` seam so the
tests exercise the real row assembly and the never-raise failure recording without
network access. `services.get_settings` is monkeypatched because the real one is
lru_cached over .env.
"""

from datetime import date, datetime
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app import services
from backend.app.bootstrap import seed_db
from backend.app.config import Settings
from backend.app.db import Base
from backend.app.models import AttendanceRecord, SheetSyncRun
from backend.app.services import get_or_create_person, sync_attendance_to_sheet


def make_settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "unit-test-jwt-secret-0123456789",
        "viper_token": "unit-test-viper-token-0123456789",
        "google_credentials_path": None,
        "google_sheet_id": None,
    }
    values.update(overrides)
    return Settings(**values)


def make_db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    session.commit()
    return session


def _seed_record(db: Session) -> AttendanceRecord:
    person = get_or_create_person(db, "oliver", "Oliver")
    record = AttendanceRecord(
        person_id=person.id,
        shift_date=date(2026, 6, 1),
        status="late",
        check_in_at=datetime(2026, 6, 1, 18, 10),
        minutes_late=10,
        chase_state="none",
        notes="traffic",
    )
    db.add(record)
    db.commit()
    return record


def test_sync_records_failed_run_when_unconfigured(monkeypatch) -> None:
    """No credentials/sheet configured → a failed SheetSyncRun is recorded and
    returned; the function must never raise (callers rely on that contract)."""
    db = make_db()
    monkeypatch.setattr(services, "get_settings", lambda: make_settings())

    run = sync_attendance_to_sheet(db)

    assert run.status == "failed"
    assert "not configured" in run.error_message
    assert run.finished_at >= run.started_at
    # The failed run is persisted, not just returned.
    assert db.scalar(select(SheetSyncRun)).status == "failed"


def test_sync_records_failed_run_when_sheets_api_raises(monkeypatch) -> None:
    """A mid-flight Google API error is swallowed into a failed run with the
    original message preserved for the ops surface."""
    db = make_db()
    _seed_record(db)
    monkeypatch.setattr(
        services,
        "get_settings",
        lambda: make_settings(google_credentials_path="/tmp/creds.json", google_sheet_id="sheet123"),
    )
    monkeypatch.setattr(services.Credentials, "from_service_account_file", MagicMock(return_value=object()))

    def broken_build(*args, **kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(services, "build", broken_build)

    run = sync_attendance_to_sheet(db)

    assert run.status == "failed"
    assert "quota exceeded" in run.error_message


def test_sync_success_pushes_header_plus_rows(monkeypatch) -> None:
    """Happy path: the values pushed to the sheet are the header row plus one row
    per DB record, targeting Attendance!A1, and a success run is recorded."""
    db = make_db()
    _seed_record(db)
    monkeypatch.setattr(
        services,
        "get_settings",
        lambda: make_settings(google_credentials_path="/tmp/creds.json", google_sheet_id="sheet123"),
    )
    monkeypatch.setattr(services.Credentials, "from_service_account_file", MagicMock(return_value=object()))

    captured: dict = {}
    fake_service = MagicMock()

    def capture_update(**kwargs):
        captured.update(kwargs)
        return MagicMock(execute=MagicMock(return_value={}))

    fake_service.spreadsheets.return_value.values.return_value.update.side_effect = capture_update
    monkeypatch.setattr(services, "build", lambda *args, **kwargs: fake_service)

    run = sync_attendance_to_sheet(db)

    assert run.status == "success"
    assert run.error_message is None
    assert captured["spreadsheetId"] == "sheet123"
    assert captured["range"] == "Attendance!A1"
    values = captured["body"]["values"]
    assert values[0][:3] == ["shift_date", "person", "status"]
    assert values[1][0] == "2026-06-01"
    assert values[1][1] == "Oliver"
    assert values[1][2] == "late"
    assert len(values) == 2  # header + exactly the one seeded record
    assert db.scalar(select(SheetSyncRun)).status == "success"
