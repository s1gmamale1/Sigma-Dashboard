import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import check_password, hash_password, require_viper
from backend.app.config import Settings
from backend.app.db import Base, get_db


def make_settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "unit-test-jwt-secret-0123456789",
        "viper_token": "unit-test-viper-token-0123456789",
        "admin_password": "correct-horse-battery",
        "admin_password_hash": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_hash_and_check_password_round_trip() -> None:
    digest = hash_password("correct-horse-battery")
    assert digest.startswith("$2b$")
    assert check_password("correct-horse-battery", digest) is True
    assert check_password("wrong", digest) is False
    # An over-long password is rejected, never silently truncated.
    assert check_password("x" * 100, digest) is False
    with pytest.raises(ValueError):
        hash_password("x" * 100)


def test_require_viper_accepts_and_rejects() -> None:
    settings = make_settings()
    assert require_viper("unit-test-viper-token-0123456789", None, settings) == "viper"
    with pytest.raises(HTTPException):
        require_viper("wrong-token", None, settings)
    with pytest.raises(HTTPException):
        require_viper(None, None, settings)


def test_placeholder_secrets_rejected() -> None:
    from backend.app.config import validate_runtime_secrets

    with pytest.raises(RuntimeError, match="SIGMA_JWT_SECRET"):
        validate_runtime_secrets(make_settings(jwt_secret="change-me-in-env-1234"))
    with pytest.raises(RuntimeError, match="SIGMA_VIPER_TOKEN"):
        validate_runtime_secrets(make_settings(viper_token="change-me-viper-token"))
    validate_runtime_secrets(make_settings())  # real-looking secrets pass


def test_login_rate_limited_after_five_attempts() -> None:
    from fastapi.testclient import TestClient

    from backend.app import ratelimit
    from backend.app.config import get_settings
    from backend.app.main import app

    # Self-contained empty users table so login can query without touching the real DB.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)

    app.dependency_overrides[get_settings] = lambda: make_settings()
    app.dependency_overrides[get_db] = lambda: (yield session)
    ratelimit.reset()
    try:
        client = TestClient(app)
        for _ in range(5):
            response = client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
            )
            assert response.status_code == 401
        response = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 429
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)
        ratelimit.reset()
