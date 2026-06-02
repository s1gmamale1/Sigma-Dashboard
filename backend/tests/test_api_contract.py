from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.bootstrap import seed_db
from backend.app.config import Settings
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.auth import require_admin
from backend.app.auth import verify_password


def client_with_db() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    session.commit()

    def override_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: "admin"
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


def test_bcrypt_admin_hash_verification() -> None:
    settings = Settings(
        jwt_secret="test-secret-change-me-32",
        viper_token="test-viper-token-change-me-32",
        admin_password_hash="$2b$12$b5U.pKbL52ULaaF3AfYSd.hoWwwGoXaoTXNC/TZK59ZPKtb/3uwSq",
    )

    assert verify_password(settings, "short-test-password")
    assert not verify_password(settings, "wrong-password")
