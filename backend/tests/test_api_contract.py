from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.bootstrap import seed_db
from backend.app.models import Person
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.auth import (
    check_password,
    hash_password,
    require_admin,
    require_edit,
    require_view,
    require_viper,
)


def client_with_db() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    session.add(Person(slug="abdul", display_name="Abdul", active=True, sort_order=1))
    session.commit()

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    app.dependency_overrides[require_view] = lambda: "admin"
    app.dependency_overrides[require_edit] = lambda: "admin"
    app.dependency_overrides[require_viper] = lambda: "viper"
    return TestClient(app)


def test_viper_rejects_unknown_fields() -> None:
    client = client_with_db()
    response = client.post(
        "/api/v1/viper/attendance",
        headers={"X-Viper-Token": "change-me-viper-token"},
        json={
            "person": {"slug": "abdul", "display_name": "Abdul"},
            "shift_date": "2026-06-01",
            "check_in_at": datetime(2026, 6, 1, 18, 0, tzinfo=ZoneInfo("Asia/Tashkent")).isoformat(),
            "unexpected": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_viper_can_write_and_admin_can_read_with_envelope() -> None:
    client = client_with_db()
    write = client.post(
        "/api/v1/viper/attendance",
        headers={"X-Viper-Token": "change-me-viper-token"},
        json={
            "person": {"slug": "abdul", "display_name": "Abdul"},
            "shift_date": date(2026, 6, 1).isoformat(),
            "check_in_at": datetime(2026, 6, 1, 18, 0, tzinfo=ZoneInfo("Asia/Tashkent")).isoformat(),
        },
    )
    assert write.status_code == 200
    read = client.get("/api/v1/attendance/today?shift_date=2026-06-01")
    body = read.json()

    assert read.status_code == 200
    assert body["error"] is None
    assert body["data"][0]["person"]["slug"] == "abdul"


def test_bcrypt_password_hash_verification() -> None:
    digest = hash_password("short-test-password")
    assert check_password("short-test-password", digest)
    assert not check_password("wrong-password", digest)


def test_viper_evaluation_rejects_noncanonical_grade() -> None:
    client = client_with_db()
    payload = {
        "person": {"slug": "abdul", "display_name": "Abdul"},
        "period_start": "2026-06-02",
        "period_end": "2026-06-07",
        "grade": "good",  # lowercase drift — must be rejected
    }
    response = client.post("/api/v1/viper/evaluation", json=payload)
    assert response.status_code == 422
    response = client.post("/api/v1/viper/evaluation", json={**payload, "grade": "Good"})
    assert response.status_code == 200


def test_viper_rejects_unknown_person_slug() -> None:
    client = client_with_db()
    response = client.post(
        "/api/v1/viper/report",
        json={
            "person": {"slug": "olivr", "display_name": "Olivr"},  # typo slug
            "report_date": "2026-06-03",
            "summary": "did things",
        },
    )
    assert response.status_code == 422
    assert "olivr" in response.json()["error"]["message"]


def test_viper_goal_rejects_unknown_owner() -> None:
    client = client_with_db()
    response = client.post(
        "/api/v1/viper/goal",
        json={"slug": "hw-notion", "title": "Notion integration", "owner_slug": "olivr"},
    )
    assert response.status_code == 422


def test_viper_report_rating_accepts_0_100_rejects_beyond() -> None:
    client = client_with_db()
    payload = {
        "person": {"slug": "abdul", "display_name": "Abdul"},
        "report_date": "2026-06-04",
        "summary": "scored work",
    }
    assert client.post("/api/v1/viper/report", json={**payload, "rating": 0}).status_code == 200
    assert client.post("/api/v1/viper/report", json={**payload, "rating": 100}).status_code == 200
    assert client.post("/api/v1/viper/report", json={**payload, "rating": 101}).status_code == 422
    assert client.post("/api/v1/viper/report", json={**payload, "rating": -1}).status_code == 422


def test_daily_reports_meta_latest_on_seeded_date() -> None:
    client = client_with_db()
    write = client.post(
        "/api/v1/viper/report",
        json={
            "person": {"slug": "abdul", "display_name": "Abdul"},
            "report_date": "2026-06-05",
            "summary": "shipped the meta hint",
            "rating": 88,
        },
    )
    assert write.status_code == 200

    read = client.get("/api/v1/reports/daily?date=2026-06-05")
    body = read.json()

    assert read.status_code == 200
    assert body["error"] is None
    assert body["data"]  # non-empty: the queried date has a report
    assert body["meta"]["latest_report_date"] == "2026-06-05"


def test_daily_reports_meta_latest_falls_back_on_empty_date() -> None:
    client = client_with_db()
    write = client.post(
        "/api/v1/viper/report",
        json={
            "person": {"slug": "abdul", "display_name": "Abdul"},
            "report_date": "2026-06-05",
            "summary": "the most recent report on or before the future query",
            "rating": 51,
        },
    )
    assert write.status_code == 200

    read = client.get("/api/v1/reports/daily?date=2026-06-09")
    body = read.json()

    assert read.status_code == 200
    assert body["error"] is None
    assert body["data"] == []  # the queried (later) date has no reports
    assert body["meta"]["latest_report_date"] == "2026-06-05"  # fallback to most recent prior


def _stub_sync_run(status: str, message: str, run_id: int | None):
    from backend.app.db import utc_now
    from backend.app.models import SheetSyncRun

    run = SheetSyncRun(
        sync_type="attendance_import",
        status=status,
        started_at=utc_now(),
        finished_at=utc_now(),
        error_message=message,
    )
    if run_id is not None:
        run.id = run_id
    return run


def test_import_sheet_endpoint_returns_persisted_success(monkeypatch) -> None:
    from backend.app import routes
    from backend.app.auth import require_edit_or_viper

    client = client_with_db()
    app.dependency_overrides[require_edit_or_viper] = lambda: "viper"
    monkeypatch.setattr(
        routes, "import_attendance_sheet", lambda settings, db: _stub_sync_run("success", "imported 3 of 3 rows", 42)
    )

    resp = client.post("/api/v1/attendance/import-sheet")
    body = resp.json()

    assert resp.status_code == 200
    assert body["error"] is None
    assert body["data"]["id"] == 42
    assert body["data"]["status"] == "success"


def test_import_sheet_endpoint_tolerates_unpersisted_failed_run(monkeypatch) -> None:
    """The doubly-degraded path (import couldn't even persist the failed run → id=None) must
    still return 200 with a failed result, never a 500 — the 'endpoint can't 500' guarantee."""
    from backend.app import routes
    from backend.app.auth import require_edit_or_viper

    client = client_with_db()
    app.dependency_overrides[require_edit_or_viper] = lambda: "viper"
    monkeypatch.setattr(
        routes, "import_attendance_sheet", lambda settings, db: _stub_sync_run("failed", "database is locked", None)
    )

    resp = client.post("/api/v1/attendance/import-sheet")
    body = resp.json()

    assert resp.status_code == 200          # NOT 500, even though the run has no id
    assert body["error"] is None
    assert body["data"]["id"] is None
    assert body["data"]["status"] == "failed"
    assert body["data"]["error_message"] == "database is locked"
