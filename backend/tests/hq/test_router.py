import json

from fastapi.testclient import TestClient

from backend.app.auth import require_view
from backend.app.hq.adapters.mock import MockAdapter
from backend.app.hq.adapters.sigmacontrol import SigmaControlAdapter
from backend.app.hq.router import get_hq_service
from backend.app.hq.service import HQService
from backend.app.main import app

ENDPOINTS = [
    "overview",
    "workers",
    "sessions",
    "swarms",
    "projects",
    "tasks",
    "blockers",
    "heartbeats",
]


def _client(service: HQService) -> TestClient:
    app.dependency_overrides[require_view] = lambda: "admin"
    app.dependency_overrides[get_hq_service] = lambda: service
    return TestClient(app)


def test_overview_200_and_shape() -> None:
    client = _client(HQService([MockAdapter()]))
    r = client.get("/api/v1/hq/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    assert body["data"]["workers_total"] >= 1
    assert "mock" in body["data"]["sources"]
    assert "generated_at" in body["meta"]


def test_workers_are_labeled_with_source() -> None:
    client = _client(HQService([MockAdapter()]))
    data = client.get("/api/v1/hq/workers").json()["data"]
    assert len(data) >= 1
    assert all(w["source"] == "mock" for w in data)


def test_all_endpoints_200() -> None:
    client = _client(HQService([MockAdapter()]))
    for ep in ENDPOINTS:
        assert client.get(f"/api/v1/hq/{ep}").status_code == 200


def test_endpoints_require_auth() -> None:
    # No require_view override → real auth runs → 401 without a bearer token.
    app.dependency_overrides[get_hq_service] = lambda: HQService([MockAdapter()])
    client = TestClient(app)
    assert client.get("/api/v1/hq/overview").status_code == 401
    assert client.get("/api/v1/hq/workers").status_code == 401


def test_no_secret_shaped_values_leak_end_to_end(tmp_path) -> None:
    p = tmp_path / "sc.json"
    p.write_text(
        json.dumps(
            {
                "projects": [
                    {"id": "x", "name": "X", "slug": "x", "api_token": "ZZLEAKTOKENZZ"}
                ],
                "tasks": [{"id": "t", "title": "T", "password": "ZZLEAKPASSZZ"}],
            }
        )
    )
    client = _client(HQService([SigmaControlAdapter(str(p))]))
    for ep in ENDPOINTS:
        text = client.get(f"/api/v1/hq/{ep}").text
        assert "ZZLEAKTOKENZZ" not in text
        assert "ZZLEAKPASSZZ" not in text
