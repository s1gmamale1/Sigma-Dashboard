from fastapi.testclient import TestClient

from backend.app.auth import require_edit
from backend.app.config import Settings, get_settings
from backend.app.main import app


def _authed() -> None:
    app.dependency_overrides[require_edit] = lambda: "admin"


def _enabled_settings() -> Settings:
    return Settings(hq_allow_actions=True)


def test_actions_disabled_by_default() -> None:
    _authed()
    client = TestClient(app)
    r = client.post("/api/v1/hq/actions/stop_worker", json={"id": "x"})
    assert r.status_code == 403


def test_actions_require_signoff_even_when_enabled() -> None:
    _authed()
    app.dependency_overrides[get_settings] = _enabled_settings
    client = TestClient(app)
    r = client.post("/api/v1/hq/actions/stop_worker", json={"id": "x"})
    assert r.status_code == 403  # enabled but no X-Sigma-Signoff


def test_actions_enabled_with_signoff_returns_501() -> None:
    _authed()
    app.dependency_overrides[get_settings] = _enabled_settings
    client = TestClient(app)
    r = client.post(
        "/api/v1/hq/actions/stop_worker",
        json={"id": "x"},
        headers={"X-Sigma-Signoff": "leo"},
    )
    assert r.status_code == 501  # recognized but not implemented — no mutation


def test_actions_require_auth() -> None:
    client = TestClient(app)  # no auth override
    r = client.post("/api/v1/hq/actions/stop_worker", json={"id": "x"})
    assert r.status_code == 401
