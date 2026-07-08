"""Tests for the dashboard Google Sheets importer (backend/app/google_sheets.py).

The Google APIs are faked at the `_service` boundary with MagicMock chains that
mirror the discovery-client call shape (`drive.files().list(...).execute()`), so
these tests exercise the real header-normalization, tab-dispatch, and row-import
logic against an in-memory DB without any network access.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app import google_sheets as G
from backend.app.bootstrap import seed_db
from backend.app.config import Settings
from backend.app.db import Base
from backend.app.google_sheets import GoogleSheetError, _normalize_header, resolve_spreadsheet_id
from backend.app.models import AttendanceRecord, Goal, Person
from backend.app.services import get_or_create_person


def make_settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "unit-test-jwt-secret-0123456789",
        "viper_token": "unit-test-viper-token-0123456789",
        # Explicit init kwargs win over .env, so a developer's real Google config
        # can never leak into these tests.
        "google_credentials_path": None,
        "google_sheet_id": None,
        "google_sheet_name": "HR Department",
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


def _fake_drive(files: list[dict]) -> MagicMock:
    drive = MagicMock()
    drive.files.return_value.list.return_value.execute.return_value = {"files": files}
    return drive


def _fake_sheets(tabs: dict[str, list[list[str]]]) -> MagicMock:
    """Fake sheets service serving the given {tab_title: grid rows} content."""
    sheets = MagicMock()
    sheets.spreadsheets.return_value.get.return_value.execute.return_value = {
        "properties": {"title": "HR Department"},
        "sheets": [
            {"properties": {"title": title, "gridProperties": {"rowCount": len(rows) or 1}}}
            for title, rows in tabs.items()
        ],
    }
    sheets.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value = {
        "valueRanges": [{"values": rows} for rows in tabs.values()]
    }
    return sheets


def test_normalize_header_aliases_and_cleanup() -> None:
    assert _normalize_header("Check-In") == "check_in_at"
    assert _normalize_header("  Full Name ") == "display_name"
    assert _normalize_header("Late Minutes") == "minutes_late"
    assert _normalize_header("Employee") == "person"
    assert _normalize_header("GOAL") == "slug"
    # Separator collapsing: spaces/dashes/dots/slashes fold to single underscores.
    assert _normalize_header("shift -- date") == "shift_date"
    # Unknown headers pass through normalized, not dropped.
    assert _normalize_header("Some Custom Column") == "some_custom_column"


def test_resolve_spreadsheet_id_prefers_configured_id(monkeypatch) -> None:
    """An explicit SIGMA_GOOGLE_SHEET_ID short-circuits the Drive lookup entirely."""

    def boom(*args, **kwargs):  # would raise if the Drive API were consulted
        raise AssertionError("Drive API must not be called when google_sheet_id is set")

    monkeypatch.setattr(G, "_service", boom)
    assert resolve_spreadsheet_id(make_settings(google_sheet_id="explicit-id")) == "explicit-id"


def test_resolve_spreadsheet_id_raises_when_no_file_matches(monkeypatch) -> None:
    monkeypatch.setattr(G, "_service", lambda settings, api, version: _fake_drive([]))
    with pytest.raises(GoogleSheetError, match="Could not find"):
        resolve_spreadsheet_id(make_settings())


def test_resolve_spreadsheet_id_raises_on_multiple_matches(monkeypatch) -> None:
    """Two files sharing the configured name must error, never silently pick one."""
    files = [{"id": "a", "name": "HR Department"}, {"id": "b", "name": "HR Department"}]
    monkeypatch.setattr(G, "_service", lambda settings, api, version: _fake_drive(files))
    with pytest.raises(GoogleSheetError, match="multiple spreadsheets"):
        resolve_spreadsheet_id(make_settings())


def test_import_dispatches_attendance_tab_and_persists(monkeypatch) -> None:
    """A tab with date+person headers routes to the attendance importer and the
    row actually lands in the DB with its status intact."""
    db = make_db()
    get_or_create_person(db, "oliver", "Oliver")
    db.commit()

    sheets = _fake_sheets(
        {
            "Attendance": [
                ["Date", "Employee", "Check-In", "Status"],
                ["2026-06-01", "Oliver", "2026-06-01T18:10:00+05:00", "late"],
            ]
        }
    )
    monkeypatch.setattr(G, "_service", lambda settings, api, version: sheets)
    result = G.import_google_sheet_dashboard_data(make_settings(google_sheet_id="sheet123"), db)

    assert result.imported["attendance"] == 1
    assert result.skipped_tabs == []
    record = db.scalar(select(AttendanceRecord))
    assert record is not None
    assert record.shift_date == date(2026, 6, 1)
    # Status is re-derived from the check-in time by the policy classifier
    # (18:10 vs the 18:00 shift start → late by 10), not copied from the sheet.
    assert record.status == "late"
    assert record.minutes_late == 10
    assert db.get(Person, record.person_id).slug == "oliver"


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="KNOWN BUG (WISHLIST 2026-07-08): _parse_datetime returns a naive datetime "
    "for a designator-less sheet cell, and calculate_attendance_status subtracts the "
    "tz-aware shift start — the whole dashboard import 500s. Fix: localize naive "
    "parsed datetimes to settings.timezone. When fixed, this test XPASSes (strict) — "
    "promote it to a plain test asserting status == 'late'.",
)
def test_import_attendance_naive_checkin_datetime(monkeypatch) -> None:
    """A bare '2026-06-01T18:10:00' check-in cell — the most natural sheet format —
    must import as a 10-minute late, not crash the import."""
    db = make_db()
    get_or_create_person(db, "oliver", "Oliver")
    db.commit()
    sheets = _fake_sheets(
        {
            "Attendance": [
                ["Date", "Employee", "Check-In"],
                ["2026-06-01", "Oliver", "2026-06-01T18:10:00"],
            ]
        }
    )
    monkeypatch.setattr(G, "_service", lambda settings, api, version: sheets)
    G.import_google_sheet_dashboard_data(make_settings(google_sheet_id="sheet123"), db)

    record = db.scalar(select(AttendanceRecord))
    assert record is not None and record.status == "late" and record.minutes_late == 10


def test_import_attendance_explicit_late_without_checkin_derives_no_show(monkeypatch) -> None:
    """calculate_attendance_status only honors explicit off_day/absent; any other
    sheet status with no check-in time derives to no_show — the harsher outcome.
    Pinned deliberately: if this classifier contract changes, this test must too."""
    db = make_db()
    get_or_create_person(db, "oliver", "Oliver")
    db.commit()
    sheets = _fake_sheets(
        {
            "Attendance": [
                ["Date", "Employee", "Status"],
                ["2026-06-01", "Oliver", "late"],
                ["2026-06-02", "Oliver", "absent"],
            ]
        }
    )
    monkeypatch.setattr(G, "_service", lambda settings, api, version: sheets)
    G.import_google_sheet_dashboard_data(make_settings(google_sheet_id="sheet123"), db)

    by_date = {r.shift_date: r for r in db.scalars(select(AttendanceRecord))}
    assert by_date[date(2026, 6, 1)].status == "no_show"  # "late" ignored without a check-in
    assert by_date[date(2026, 6, 2)].status == "absent"  # explicit absent is honored


def test_import_dispatches_goals_tab(monkeypatch) -> None:
    """The 'Goal' header aliases to slug and the tab routes to the goal importer."""
    db = make_db()
    sheets = _fake_sheets(
        {
            "Goals": [
                ["Title", "Goal", "Progress"],
                ["Ship v2", "ship-v2", "40"],
            ]
        }
    )
    monkeypatch.setattr(G, "_service", lambda settings, api, version: sheets)
    result = G.import_google_sheet_dashboard_data(make_settings(google_sheet_id="sheet123"), db)

    assert result.imported["goals"] == 1
    goal = db.scalar(select(Goal).where(Goal.slug == "ship-v2"))
    assert goal is not None
    assert goal.title == "Ship v2"
    assert goal.progress_percent == 40


def test_import_skips_short_and_unrecognized_tabs(monkeypatch) -> None:
    """Header-only tabs and unknown header sets are reported in skipped_tabs, not
    silently dropped or misfiled into a data area."""
    db = make_db()
    sheets = _fake_sheets(
        {
            "Empty": [["Date", "Employee"]],  # header only, no data rows
            "Mystery": [["foo", "bar"], ["1", "2"]],
        }
    )
    monkeypatch.setattr(G, "_service", lambda settings, api, version: sheets)
    result = G.import_google_sheet_dashboard_data(make_settings(google_sheet_id="sheet123"), db)

    assert result.imported == {"attendance": 0, "reports": 0, "goals": 0, "project_conditions": 0}
    assert "Empty: not enough rows" in result.skipped_tabs
    assert "Mystery: headers not recognized" in result.skipped_tabs


def test_import_attendance_skips_rows_missing_name_or_date(monkeypatch) -> None:
    """Rows without a parseable date or a person are skipped, and an unrecognized
    status string degrades to None (re-derived) rather than importing garbage."""
    db = make_db()
    get_or_create_person(db, "oliver", "Oliver")
    db.commit()
    sheets = _fake_sheets(
        {
            "Attendance": [
                ["Date", "Employee", "Status"],
                ["not-a-date", "Oliver", "late"],  # unparseable date -> skipped
                ["2026-06-02", "", "late"],  # blank name cell -> skipped
                ["2026-06-03", "Oliver", "LATE!!"],  # bad status -> imported, status derived
            ]
        }
    )
    monkeypatch.setattr(G, "_service", lambda settings, api, version: sheets)
    result = G.import_google_sheet_dashboard_data(make_settings(google_sheet_id="sheet123"), db)

    assert result.imported["attendance"] == 1
    record = db.scalar(select(AttendanceRecord))
    assert record.shift_date == date(2026, 6, 3)
    # The unvalidated "LATE!!" string is dropped, and with no check-in the policy
    # classifier derives no_show — never stored verbatim.
    assert record.status == "no_show"


def test_parse_helpers_edge_cases() -> None:
    assert G._parse_date("2026-06-01") == date(2026, 6, 1)
    assert G._parse_date("01.06.2026") == date(2026, 6, 1)
    assert G._parse_date("06/01/2026") in {date(2026, 1, 6), date(2026, 6, 1)}  # d/m tried before m/d
    assert G._parse_date("garbage") is None
    assert G._parse_int("1 250 000 uzs") == 1250000
    assert G._parse_int("", default=7) == 7
    assert G._parse_bool("Yes") is True
    assert G._parse_bool("no") is False
    # Consecutive separators are NOT collapsed — "A / B" yields a triple hyphen.
    # Pinned as-is: slugs must stay stable or existing roster refs would break.
    assert G._slug("Class A / LMS") == "class-a---lms"
