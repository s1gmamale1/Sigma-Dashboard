"""
Integration tests for the multi-user / role system.

Uses a real in-memory DB and real bearer tokens (logs in through the API), so the
permission dependencies, the temp-password gate, and the admin guards are all
exercised end-to-end rather than bypassed with dependency overrides.
"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app import ratelimit
from backend.app.auth import hash_password
from backend.app.bootstrap import seed_db
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import User


SEED = [
    ("admin", "admin-pass", "admin", False),
    ("manager", "mgr-pass", "manager", False),
    ("viewer", "view-pass", "viewer", False),
    ("cody", "159075", "manager", True),  # temp password, must change on first login
]


def _make_client() -> TestClient:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    for username, password, role, must_change in SEED:
        session.add(
            User(
                username=username,
                display_name=username.title(),
                password_hash=hash_password(password),
                role=role,
                active=True,
                must_change_password=must_change,
            )
        )
    session.commit()

    app.dependency_overrides[get_db] = lambda: (yield session)
    ratelimit.reset()  # login is rate-limited per IP; isolate each test
    return TestClient(app)


def _login(client: TestClient, username: str, password: str):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return response


def _token(client: TestClient, username: str, password: str) -> str:
    return _login(client, username, password).json()["data"]["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def teardown_function() -> None:
    app.dependency_overrides.pop(get_db, None)
    ratelimit.reset()


def test_login_returns_role_and_must_change_flag() -> None:
    client = _make_client()
    admin = _login(client, "admin", "admin-pass").json()["data"]
    assert admin["role"] == "admin"
    assert admin["must_change_password"] is False

    cody = _login(client, "cody", "159075").json()["data"]
    assert cody["role"] == "manager"
    assert cody["must_change_password"] is True
    assert cody["display_name"] == "Cody"


def test_me_exposes_role_permissions() -> None:
    client = _make_client()
    admin = client.get("/api/v1/auth/me", headers=_bearer(_token(client, "admin", "admin-pass"))).json()["data"]
    assert "write" in admin["permissions"]["users"]

    manager = client.get("/api/v1/auth/me", headers=_bearer(_token(client, "manager", "mgr-pass"))).json()["data"]
    assert "users" not in manager["permissions"]
    assert manager["permissions"]["projects"] == ["read", "write"]


def test_manager_cannot_manage_users() -> None:
    client = _make_client()
    headers = _bearer(_token(client, "manager", "mgr-pass"))
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    create = client.post(
        "/api/v1/users",
        headers=headers,
        json={"username": "x", "display_name": "X", "role": "viewer", "temp_password": "secret1"},
    )
    assert create.status_code == 403


def test_admin_user_lifecycle() -> None:
    client = _make_client()
    headers = _bearer(_token(client, "admin", "admin-pass"))

    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={"username": "dana", "display_name": "Dana", "role": "viewer", "temp_password": "temp-pass-1"},
    )
    assert created.status_code == 200
    dana = created.json()["data"]
    assert dana["role"] == "viewer" and dana["must_change_password"] is True

    # duplicate username is rejected
    assert client.post(
        "/api/v1/users",
        headers=headers,
        json={"username": "dana", "display_name": "Dana 2", "role": "viewer", "temp_password": "temp-pass-2"},
    ).status_code == 409

    # promote dana to manager
    patched = client.patch(f"/api/v1/users/{dana['id']}", headers=headers, json={"role": "manager"})
    assert patched.status_code == 200 and patched.json()["data"]["role"] == "manager"

    # reset dana's password (forces change again)
    reset = client.post(
        f"/api/v1/users/{dana['id']}/reset-password", headers=headers, json={"temp_password": "fresh-temp-9"}
    )
    assert reset.status_code == 200 and reset.json()["data"]["must_change_password"] is True

    # delete dana
    assert client.delete(f"/api/v1/users/{dana['id']}", headers=headers).status_code == 200
    listing = client.get("/api/v1/users", headers=headers).json()["data"]
    assert "dana" not in {u["username"] for u in listing}


def test_temp_password_gate_blocks_until_changed() -> None:
    client = _make_client()
    login = _login(client, "cody", "159075").json()["data"]
    headers = _bearer(login["access_token"])

    # /me works (so the UI can detect the pending change)...
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    # ...but data routes are gated until the password is rotated.
    assert client.get("/api/v1/goals", headers=headers).status_code == 403

    changed = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "159075", "new_password": "cody-new-pass"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["must_change_password"] is False
    # gate lifted
    assert client.get("/api/v1/goals", headers=headers).status_code == 200


def test_viewer_is_read_only() -> None:
    client = _make_client()
    headers = _bearer(_token(client, "viewer", "view-pass"))
    # read OK
    assert client.get("/api/v1/goals", headers=headers).status_code == 200
    # write blocked
    write = client.post("/api/v1/projects", headers=headers, json={"title": "Nope", "open_items": []})
    assert write.status_code == 403


def test_cannot_remove_last_admin_or_self() -> None:
    client = _make_client()
    headers = _bearer(_token(client, "admin", "admin-pass"))
    users = {u["username"]: u for u in client.get("/api/v1/users", headers=headers).json()["data"]}
    admin_id = users["admin"]["id"]

    # demoting the only admin is refused
    assert client.patch(f"/api/v1/users/{admin_id}", headers=headers, json={"role": "manager"}).status_code == 409
    # disabling the only admin is refused
    assert client.patch(f"/api/v1/users/{admin_id}", headers=headers, json={"active": False}).status_code == 409
    # deleting yourself is refused
    assert client.delete(f"/api/v1/users/{admin_id}", headers=headers).status_code == 400
