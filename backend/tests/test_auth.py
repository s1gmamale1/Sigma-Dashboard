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
