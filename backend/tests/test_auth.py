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


def test_disabled_user_with_valid_token_is_rejected() -> None:
    """A still-unexpired JWT for a since-disabled account must 403 on every request —
    this per-request DB check is the actual enforcement point for 'disable user'."""
    from sqlalchemy import select

    from backend.app.auth import create_access_token, get_current_user
    from backend.app.models import User

    settings = make_settings()
    session = _session_with_user("admin")
    token, _ = create_access_token(settings, "someone", "admin")

    # Token is valid while the account is active…
    assert get_current_user(_bearer(token), settings, session).username == "someone"

    # …and the very same token is rejected the moment the account is disabled.
    user = session.scalar(select(User).where(User.username == "someone"))
    user.active = False
    session.commit()
    with pytest.raises(HTTPException) as exc:
        get_current_user(_bearer(token), settings, session)
    assert exc.value.status_code == 403
    assert "disabled" in str(exc.value.detail)


def test_expired_token_is_rejected() -> None:
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from backend.app.auth import get_current_user

    settings = make_settings()
    session = _session_with_user("admin")
    expired = jwt.encode(
        {
            "sub": "someone",
            "role": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as exc:
        get_current_user(_bearer(expired), settings, session)
    assert exc.value.status_code == 401


def test_token_signed_with_wrong_secret_is_rejected() -> None:
    from jose import jwt

    from backend.app.auth import get_current_user

    settings = make_settings()
    session = _session_with_user("admin")
    forged = jwt.encode(
        {"sub": "someone", "role": "admin"},
        "attacker-controlled-secret-000000",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as exc:
        get_current_user(_bearer(forged), settings, session)
    assert exc.value.status_code == 401
