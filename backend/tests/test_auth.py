import pytest
from fastapi import HTTPException

from backend.app.auth import require_viper, verify_password
from backend.app.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "unit-test-jwt-secret-0123456789",
        "viper_token": "unit-test-viper-token-0123456789",
        "admin_password": "correct-horse-battery",
        "admin_password_hash": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_verify_password_plaintext_fallback() -> None:
    settings = make_settings()
    assert verify_password(settings, "correct-horse-battery") is True
    assert verify_password(settings, "wrong") is False
    assert verify_password(make_settings(admin_password=None), "anything") is False


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

    app.dependency_overrides[get_settings] = lambda: make_settings()
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
        ratelimit.reset()
