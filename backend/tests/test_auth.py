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


def _bearer(token: str):
    from fastapi.security import HTTPAuthorizationCredentials

    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _session_with_user(role: str) -> Session:
    from backend.app.models import User

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        User(
            username="someone",
            display_name="Some One",
            password_hash="x",
            role=role,
            active=True,
            must_change_password=False,
        )
    )
    session.commit()
    return session


def test_require_edit_or_viper_accepts_viper_token() -> None:
    """The ingest agent can trigger the on-demand import with the Viper secret —
    via the X-Viper-Token header or a bearer of the same secret. The DB is never
    consulted on this path, so a None session is fine."""
    from backend.app.auth import require_edit_or_viper

    settings = make_settings()
    assert require_edit_or_viper("unit-test-viper-token-0123456789", None, settings, None) == "viper"
    assert require_edit_or_viper(None, _bearer("unit-test-viper-token-0123456789"), settings, None) == "viper"


def test_require_edit_or_viper_rejects_missing_or_wrong_credentials() -> None:
    from backend.app.auth import require_edit_or_viper

    settings = make_settings()
    with pytest.raises(HTTPException) as missing:  # no credentials at all
        require_edit_or_viper(None, None, settings, None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException):  # a bearer that is neither the Viper token nor a valid JWT
        require_edit_or_viper(None, _bearer("not-a-real-token"), settings, None)

    # A wrong X-Viper-Token with no JWT reports the Viper failure specifically,
    # not a misleading "Missing bearer token".
    with pytest.raises(HTTPException) as wrong_viper:
        require_edit_or_viper("wrong-viper-token", None, settings, None)
    assert wrong_viper.value.status_code == 401
    assert "Viper" in str(wrong_viper.value.detail)


def test_require_edit_or_viper_accepts_edit_user_and_rejects_viewer() -> None:
    from backend.app.auth import create_access_token, require_edit_or_viper

    settings = make_settings()

    admin_session = _session_with_user("admin")
    admin_token, _ = create_access_token(settings, "someone", "admin")
    assert require_edit_or_viper(None, _bearer(admin_token), settings, admin_session) == "someone"

    viewer_session = _session_with_user("viewer")
    viewer_token, _ = create_access_token(settings, "someone", "viewer")
    with pytest.raises(HTTPException) as exc:
        require_edit_or_viper(None, _bearer(viewer_token), settings, viewer_session)
    assert exc.value.status_code == 403
