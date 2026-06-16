import pytest

from backend.app.config import Settings


def test_gateway_session_key_is_three_part():
    s = Settings(gateway_agent="viper", gateway_session="dashboard")
    assert s.gateway_session_key == "agent:viper:dashboard"


def test_enabled_assistant_requires_real_token():
    s = Settings(assistant_enabled=True, gateway_token="")
    with pytest.raises(Exception):
        s.validate_runtime_secrets()
