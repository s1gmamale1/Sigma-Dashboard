from datetime import date, datetime
from functools import lru_cache
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from .config import Settings
from .schemas import (
    GoogleSheetImportResult,
    GoogleSheetPreview,
    GoogleSheetTabPreview,
    ViperAttendanceUpsert,
    ViperGoalUpsert,
    ViperPersonRef,
    ViperProjectConditionUpsert,
    ViperReportUpsert,
)
from .services import upsert_attendance, upsert_goal, upsert_project_condition, upsert_report

SHEETS_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleSheetError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _load_credentials(credentials_path: str) -> Credentials:
    """Read + parse the service-account file once per path.

    The interval auto-sync now runs ~144x/day; without caching, each run re-read the
    JSON off disk and re-parsed the RSA key. Cached by path so a rotated-path config
    still reloads. The returned Credentials refreshes its own access tokens, and imports
    are serialized by ``attendance_sheet._import_lock``, so reuse is safe.
    """
    return Credentials.from_service_account_file(credentials_path, scopes=SCOPES)


def _credentials(settings: Settings) -> Credentials:
    if not settings.google_credentials_path:
        raise GoogleSheetError("SIGMA_GOOGLE_CREDENTIALS_PATH is not configured")
    return _load_credentials(settings.google_credentials_path)


def _quote_sheet_name(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def _service(settings: Settings, api: str, version: str):
    return build(api, version, credentials=_credentials(settings), cache_discovery=False)


def resolve_spreadsheet_id(settings: Settings) -> str:
    if settings.google_sheet_id:
        return settings.google_sheet_id

    drive = _service(settings, "drive", "v3")
    safe_name = settings.google_sheet_name.replace("'", "\\'")
    try:
        response = (
            drive.files()
            .list(
                q=f"name = '{safe_name}' and mimeType = '{SHEETS_MIME_TYPE}' and trashed = false",
                spaces="drive",
                fields="files(id,name)",
                pageSize=10,
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleSheetError(_google_error_message(exc)) from exc
    files = response.get("files", [])
    if not files:
        raise GoogleSheetError(
            f"Could not find a Google spreadsheet named '{settings.google_sheet_name}' shared with the service account"
        )
    if len(files) > 1:
        raise GoogleSheetError(
            f"Found multiple spreadsheets named '{settings.google_sheet_name}'; set SIGMA_GOOGLE_SHEET_ID explicitly"
        )
    return files[0]["id"]


def get_sheet_preview(settings: Settings, sample_rows: int = 8) -> GoogleSheetPreview:
    spreadsheet_id = resolve_spreadsheet_id(settings)
    sheets = _service(settings, "sheets", "v4")
    try:
        metadata = (
            sheets.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="properties(title),sheets(properties(title,gridProperties(rowCount,columnCount)))",
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleSheetError(_google_error_message(exc)) from exc

    tab_props = [sheet["properties"] for sheet in metadata.get("sheets", [])]
    ranges = [f"{_quote_sheet_name(props['title'])}!A1:Z{sample_rows}" for props in tab_props]
    try:
        batch = (
            sheets.spreadsheets()
            .values()
            .batchGet(spreadsheetId=spreadsheet_id, ranges=ranges, majorDimension="ROWS")
            .execute()
        )
    except HttpError as exc:
        raise GoogleSheetError(_google_error_message(exc)) from exc
    value_ranges = batch.get("valueRanges", [])

    tabs = []
    for index, sheet in enumerate(metadata.get("sheets", [])):
        props = sheet["properties"]
        title = props["title"]
        grid = props.get("gridProperties", {})
        sample_range = f"{_quote_sheet_name(title)}!A1:Z{sample_rows}"
        values = value_ranges[index].get("values", []) if index < len(value_ranges) else []
        tabs.append(
            GoogleSheetTabPreview(
                title=title,
                row_count=grid.get("rowCount", 0),
                column_count=grid.get("columnCount", 0),
                sample_range=sample_range,
                values=[[str(cell) for cell in row] for row in values],
            )
        )
    return GoogleSheetPreview(
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=metadata.get("properties", {}).get("title", settings.google_sheet_name),
        configured_name=settings.google_sheet_name,
        tabs=tabs,
    )


def import_google_sheet_dashboard_data(settings: Settings, db: Session) -> GoogleSheetImportResult:
    spreadsheet_id = resolve_spreadsheet_id(settings)
    sheets = _service(settings, "sheets", "v4")
    try:
        metadata = (
            sheets.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="properties(title),sheets(properties(title,gridProperties(rowCount)))",
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleSheetError(_google_error_message(exc)) from exc
    imported = {"attendance": 0, "reports": 0, "goals": 0, "project_conditions": 0}
    skipped_tabs: list[str] = []
    notes: list[str] = [
        "Importer is header-based until exact tab names and cell coordinates are provided.",
        "Recognized headers are documented in backend/app/google_sheets.py.",
    ]

    tab_specs = []
    for sheet in metadata.get("sheets", []):
        title = sheet["properties"]["title"]
        row_count = min(int(sheet["properties"].get("gridProperties", {}).get("rowCount", 1000)), 2000)
        tab_specs.append((title, f"{_quote_sheet_name(title)}!A1:Z{row_count}"))
    try:
        batch = (
            sheets.spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=[spec[1] for spec in tab_specs],
                majorDimension="ROWS",
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleSheetError(_google_error_message(exc)) from exc
    value_ranges = batch.get("valueRanges", [])

    for index, (title, _) in enumerate(tab_specs):
        values = value_ranges[index].get("values", []) if index < len(value_ranges) else []
        if len(values) < 2:
            skipped_tabs.append(f"{title}: not enough rows")
            continue
        headers = [_normalize_header(cell) for cell in values[0]]
        rows = [_row_dict(headers, row) for row in values[1:]]

        if _has_any(headers, {"shift_date", "date"}) and _has_any(headers, {"person", "name", "display_name"}):
            imported["attendance"] += _import_attendance_rows(db, rows)
        elif _has_any(headers, {"report_date", "date"}) and _has_any(headers, {"summary", "report"}):
            imported["reports"] += _import_report_rows(db, rows)
        elif "title" in headers and _has_any(headers, {"slug", "goal_slug", "goal"}):
            imported["goals"] += _import_goal_rows(db, rows)
        elif _has_any(headers, {"topic_id", "topic"}) and _has_any(headers, {"summary", "condition"}):
            imported["project_conditions"] += _import_project_condition_rows(db, rows)
        else:
            skipped_tabs.append(f"{title}: headers not recognized")

    db.flush()
    return GoogleSheetImportResult(
        spreadsheet_id=spreadsheet_id,
        spreadsheet_title=metadata.get("properties", {}).get("title", settings.google_sheet_name),
        imported=imported,
        skipped_tabs=skipped_tabs,
        notes=notes,
    )


def _normalize_header(value: Any) -> str:
    normalized = str(value).strip().lower()
    for char in (" ", "-", "/", "."):
        normalized = normalized.replace(char, "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    aliases = {
        "employee": "person",
        "full_name": "display_name",
        "checkin": "check_in_at",
        "check_in": "check_in_at",
        "checkout": "check_out_at",
        "check_out": "check_out_at",
        "late_minutes": "minutes_late",
        "charge": "charge_amount_uzs",
        "goal": "slug",
        "condition": "summary",
        "report": "summary",
    }
    return aliases.get(normalized, normalized)


def _google_error_message(exc: HttpError) -> str:
    status = getattr(exc.resp, "status", "unknown")
    if status == 429:
        return "Google Sheets read quota was exceeded. Wait about a minute and try again."
    return f"Google API error {status}: {exc.reason}"


def _has_any(headers: list[str], candidates: set[str]) -> bool:
    return any(header in candidates for header in headers)


def _row_dict(headers: list[str], row: list[Any]) -> dict[str, str]:
    return {
        header: str(row[index]).strip()
        for index, header in enumerate(headers)
        if header and index < len(row) and str(row[index]).strip()
    }


def _value(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if row.get(key):
            return row[key]
    return None


def _slug(value: str) -> str:
    slug = value.strip().lower()
    for char in (" ", ".", "/", "\\"):
        slug = slug.replace(char, "-")
    return "".join(char for char in slug if char.isalnum() or char == "-").strip("-") or "unknown"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        parsed_date = _parse_date(value)
        return datetime.combine(parsed_date, datetime.min.time()) if parsed_date else None


def _parse_int(value: str | None, default: int = 0) -> int:
    if not value:
        return default
    digits = "".join(char for char in value if char.isdigit() or char == "-")
    return int(digits) if digits else default


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _parse_bool(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "y", "missing"})


def _import_attendance_rows(db: Session, rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        name = _value(row, "display_name", "person", "name")
        shift_date = _parse_date(_value(row, "shift_date", "date"))
        if not name or not shift_date:
            continue
        status = _value(row, "status")
        upsert_attendance(
            db,
            ViperAttendanceUpsert(
                person=ViperPersonRef(slug=_value(row, "slug") or _slug(name), display_name=name),
                shift_date=shift_date,
                check_in_at=_parse_datetime(_value(row, "check_in_at")),
                check_out_at=_parse_datetime(_value(row, "check_out_at")),
                status=status if status in {"on_time", "late", "late_15", "no_show", "absent"} else None,
                notes=_value(row, "notes"),
            ),
        )
        count += 1
    return count


def _import_report_rows(db: Session, rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        name = _value(row, "display_name", "person", "name")
        report_date = _parse_date(_value(row, "report_date", "date"))
        summary = _value(row, "summary")
        if not name or not report_date or not summary:
            continue
        upsert_report(
            db,
            ViperReportUpsert(
                person=ViperPersonRef(slug=_value(row, "slug") or _slug(name), display_name=name),
                report_date=report_date,
                summary=summary,
                extras=_value(row, "extras"),
                rating=_clamp(_parse_int(_value(row, "rating"), 0), 0, 100)
                if _value(row, "rating")
                else None,
                missing=_parse_bool(_value(row, "missing")),
                source_topic=_value(row, "source_topic", "topic_id", "topic"),
            ),
        )
        count += 1
    return count


def _import_goal_rows(db: Session, rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        title = _value(row, "title")
        slug = _value(row, "slug", "goal_slug") or (title and _slug(title))
        if not title or not slug:
            continue
        status = _value(row, "status") or "active"
        upsert_goal(
            db,
            ViperGoalUpsert(
                slug=slug,
                title=title,
                owner_slug=_value(row, "owner_slug"),
                topic_id=_value(row, "topic_id", "topic"),
                deadline=_parse_date(_value(row, "deadline")),
                status=status if status in {"active", "overdue", "done", "paused"} else "active",
                progress_percent=_clamp(_parse_int(_value(row, "progress_percent", "progress"), 0), 0, 100),
                progress_log=_value(row, "progress_log", "log"),
            ),
        )
        count += 1
    return count


def _import_project_condition_rows(db: Session, rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        topic_id = _value(row, "topic_id", "topic")
        summary = _value(row, "summary")
        if not topic_id or not summary:
            continue
        open_items = [
            item.strip()
            for item in (_value(row, "open_items", "items") or "").replace("\n", ",").split(",")
            if item.strip()
        ]
        upsert_project_condition(
            db,
            ViperProjectConditionUpsert(
                topic_id=topic_id,
                summary=summary,
                last_activity_at=_parse_datetime(_value(row, "last_activity_at", "updated_at")),
                open_items=open_items,
            ),
        )
        count += 1
    return count
