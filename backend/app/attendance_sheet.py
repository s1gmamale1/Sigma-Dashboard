"""Import the wide-format HR attendance tab (`Sigma Attendnace`) into the dashboard.

Layout (per the HR Department sheet):
- Column A = Date (shift-start day).
- People occupy fixed 3-column blocks starting at column B: Arrival time / Out time / Status.
- Person names are on row 2; the data starts on row 4.

The Status column is authoritative — the dashboard mirrors the 5 HR values verbatim
(On time / Late / 15+ Late / No Show / Absent → on_time / late / late_15 / no_show / absent).
The Arrival time only sets `minutes_late` and the check-in display; there is no charge concept.
Chase state and notes are admin-owned and are never overwritten on re-sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import utc_now
from .google_sheets import (
    GoogleSheetError,
    _parse_date,
    _quote_sheet_name,
    _service,
    _slug,
    resolve_spreadsheet_id,
)
from .models import AttendanceRecord, SheetSyncRun
from .services import (
    calculate_attendance_status,
    get_active_policy,
    get_or_create_person,
    shift_start_datetime,
)

PERSON_BLOCK_START = 1  # column B (0-indexed): first person's Arrival column
PERSON_BLOCK_WIDTH = 3  # Arrival, Out, Status
NAME_ROW_INDEX = 1      # row 2 (0-indexed) holds the person names
DATA_START_ROW = 4      # data begins on row 4 (1-indexed)


@dataclass
class SheetAttendanceRow:
    slug: str
    display_name: str
    shift_date: date
    arrival: str
    out: str
    status_text: str


def _parse_time(value: str) -> time | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def _combine(day: date, value: str, tz: ZoneInfo) -> datetime | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return datetime.combine(day, parsed, tzinfo=tz)


def parse_attendance_grid(values: list[list[str]]) -> list[SheetAttendanceRow]:
    """Flatten the wide grid into one row per (person, day) that has any data."""
    rows: list[SheetAttendanceRow] = []
    if len(values) < DATA_START_ROW:
        return rows

    name_row = values[NAME_ROW_INDEX] if len(values) > NAME_ROW_INDEX else []
    blocks: list[tuple[int, str, str]] = []
    col = PERSON_BLOCK_START
    while col < len(name_row):
        name = str(name_row[col]).strip()
        if not name:
            break
        blocks.append((col, _slug(name), name))
        col += PERSON_BLOCK_WIDTH

    for raw in values[DATA_START_ROW - 1:]:
        if not raw:
            continue
        day = _parse_date(str(raw[0]).strip()) if raw and str(raw[0]).strip() else None
        if day is None:
            continue
        for col, slug, name in blocks:
            arrival = str(raw[col]).strip() if col < len(raw) else ""
            out = str(raw[col + 1]).strip() if col + 1 < len(raw) else ""
            status_text = str(raw[col + 2]).strip() if col + 2 < len(raw) else ""
            if not arrival and not out and not status_text:
                continue
            rows.append(SheetAttendanceRow(slug, name, day, arrival, out, status_text))

    rows.sort(key=lambda row: row.shift_date)  # chronological → weekly-late counting is correct
    return rows


def _normalize_status(value: str) -> str:
    text = value.strip().lower().replace("-", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text


OFF_DAY_TEXT = "off day"


def _is_off_day(arrival: str, status_text: str) -> bool:
    """Viper marks scheduled days off by writing the literal 'OFF DAY' into the
    arrival cell (per-person) or status cell; either marks the day off."""
    return _normalize_status(arrival) == OFF_DAY_TEXT or _normalize_status(status_text) == OFF_DAY_TEXT


def _minutes_late(db: Session, shift_date: date, check_in_at: datetime | None) -> int:
    if check_in_at is None:
        return 0
    start = shift_start_datetime(shift_date, get_active_policy(db))
    return max(0, int((check_in_at - start).total_seconds() // 60))


def classify_sheet_row(
    db: Session,
    shift_date: date,
    check_in_at: datetime | None,
    status_text: str,
) -> tuple[str, int] | None:
    """Map a sheet row to (status, minutes_late). The sheet Status column is authoritative
    (the 5 HR values); the arrival time only sets `minutes_late` and the check-in display.
    Returns None to skip an empty row."""
    status = _normalize_status(status_text)
    mins = _minutes_late(db, shift_date, check_in_at)
    if status in {"absent", "excused"}:
        return "absent", 0
    if status in {"no show", "no_show", "noshow"}:
        return "no_show", 0
    if status in {"on time", "on_time", "ontime", "in"}:
        return "on_time", mins
    if status in {"15+ late", "15 late", "15+late", "charged"}:
        return "late_15", mins
    if status == "late":
        return "late", mins
    # No recognizable status text → derive from the arrival time.
    if check_in_at is not None:
        return calculate_attendance_status(db, shift_date, check_in_at, None)
    return None


def _upsert_row(db: Session, row: SheetAttendanceRow, tz: ZoneInfo) -> bool:
    person = get_or_create_person(db, row.slug, row.display_name)
    if _is_off_day(row.arrival, row.status_text):
        # An OFF DAY upserts a real record so a stale no_show/late imported earlier
        # for this (person, date) is overwritten, never silently kept.
        check_in: datetime | None = None
        check_out: datetime | None = None
        status, minutes_late = "off_day", 0
    else:
        check_in = _combine(row.shift_date, row.arrival, tz)
        check_out = _combine(row.shift_date, row.out, tz)
        if check_in and check_out and check_out < check_in:
            check_out = check_out + timedelta(days=1)  # shift crosses midnight (out ~03:00)

        classified = classify_sheet_row(db, row.shift_date, check_in, row.status_text)
        if classified is None:
            return False
        status, minutes_late = classified

    record = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.person_id == person.id,
            AttendanceRecord.shift_date == row.shift_date,
        )
    )
    if record is None:
        record = AttendanceRecord(
            person_id=person.id, shift_date=row.shift_date, status=status, chase_state="none"
        )
        db.add(record)
    record.check_in_at = check_in
    record.check_out_at = check_out
    record.status = status
    record.minutes_late = minutes_late
    # chase_state and notes are admin-owned — intentionally not reset on re-sync.
    db.flush()
    return True


def apply_attendance_rows(db: Session, rows: list[SheetAttendanceRow], tz: ZoneInfo) -> int:
    return sum(1 for row in rows if _upsert_row(db, row, tz))


def import_attendance_sheet(settings: Settings, db: Session) -> SheetSyncRun:
    """Fetch + parse + apply the attendance tab; records a `SheetSyncRun` either way."""
    started = utc_now()
    tz = ZoneInfo(settings.timezone)
    try:
        if not settings.google_credentials_path:
            raise GoogleSheetError("SIGMA_GOOGLE_CREDENTIALS_PATH is not configured")
        spreadsheet_id = resolve_spreadsheet_id(settings)
        sheets = _service(settings, "sheets", "v4")
        cell_range = f"{_quote_sheet_name(settings.attendance_tab)}!A1:Z2000"
        response = (
            sheets.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=cell_range, majorDimension="ROWS")
            .execute()
        )
        values = [[str(cell) for cell in row] for row in response.get("values", [])]
        rows = parse_attendance_grid(values)
        imported = apply_attendance_rows(db, rows, tz)
        run = SheetSyncRun(
            sync_type="attendance_import",
            status="success",
            started_at=started,
            finished_at=utc_now(),
            error_message=f"imported {imported} of {len(rows)} rows from '{settings.attendance_tab}'",
        )
    except Exception as exc:  # noqa: BLE001 — failures are recorded, not raised, so the scheduler survives
        run = SheetSyncRun(
            sync_type="attendance_import",
            status="failed",
            started_at=started,
            finished_at=utc_now(),
            error_message=str(exc),
        )
    db.add(run)
    db.flush()
    return run
