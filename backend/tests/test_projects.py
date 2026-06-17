"""
Route-level integration tests for the admin project endpoints.

Covers create (auto + explicit + duplicate topic_id), patch (title/summary and the
open_items done-flag round-trip), legacy open_items coercion, the log timeline
(add/delete with topic scoping), archive hiding from the board, deleting a project
that a Goal references (the goal is detached), and the 401-without-token contract.

Follows the TestClient/StaticPool/seed_db conventions of test_routes_gaps.py, but
mints a real admin JWT via create_access_token so require_admin is exercised for real.
"""
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import create_access_token, require_admin, require_viper
from backend.app.bootstrap import seed_db
from backend.app.config import get_settings
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import Goal, ProjectCondition, ProjectTopic, User


def _make_client() -> tuple[TestClient, Session]:
    """A TestClient backed by a fresh in-memory DB. Auth dependencies are NOT
    bypassed — admin requests carry a real bearer token via _auth()."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    session.add(
        User(
            username=get_settings().admin_username,
            display_name="Admin",
            password_hash="unused-for-token-auth",
            role="admin",
            active=True,
            must_change_password=False,
        )
    )
    session.commit()

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_viper, None)
    return TestClient(app), session


def _auth() -> dict[str, str]:
    settings = get_settings()
    token = create_access_token(settings, settings.admin_username, "admin")[0]
    return {"Authorization": f"Bearer {token}"}


def _topic_path(topic_id: str) -> str:
    return f"/api/v1/projects/{quote(topic_id, safe='')}"


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreateProject:
    def test_create_with_auto_generated_topic_id(self):
        client, _ = _make_client()
        response = client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={"title": "Auto Project", "open_items": []},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["title"] == "Auto Project"
        assert isinstance(data["topic_id"], str)
        assert data["topic_id"]  # non-empty, server-generated
        assert data["active"] is True

    def test_create_with_explicit_topic_id(self):
        client, _ = _make_client()
        response = client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={
                "title": "Explicit Project",
                "topic_id": "explicit-007",
                "summary": "kickoff",
                "open_items": [{"text": "first task", "done": False}],
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["topic_id"] == "explicit-007"
        assert data["summary"] == "kickoff"
        assert data["open_items"] == [{"text": "first task", "done": False}]

    def test_create_duplicate_topic_id_returns_409(self):
        client, _ = _make_client()
        first = client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={"title": "Dup", "topic_id": "dup-1", "open_items": []},
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={"title": "Dup Again", "topic_id": "dup-1", "open_items": []},
        )
        assert second.status_code == 409


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------

class TestPatchProject:
    def test_patch_title_and_summary(self):
        client, _ = _make_client()
        client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={"title": "Old Title", "topic_id": "patch-1", "summary": "old", "open_items": []},
        )
        response = client.patch(
            _topic_path("patch-1"),
            headers=_auth(),
            json={"title": "New Title", "summary": "new summary"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["title"] == "New Title"
        assert data["summary"] == "new summary"

    def test_patch_open_items_round_trips_done_flag(self):
        client, _ = _make_client()
        client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={
                "title": "Checklist",
                "topic_id": "checklist-1",
                "open_items": [{"text": "task a", "done": False}],
            },
        )
        # Toggle the task to done.
        patch = client.patch(
            _topic_path("checklist-1"),
            headers=_auth(),
            json={"open_items": [{"text": "task a", "done": True}]},
        )
        assert patch.status_code == 200

        # GET it back and assert the done flag persisted.
        listing = client.get("/api/v1/project-conditions", headers=_auth())
        assert listing.status_code == 200
        item = next(c for c in listing.json()["data"] if c["topic_id"] == "checklist-1")
        assert item["open_items"] == [{"text": "task a", "done": True}]
        assert item["open_items"][0]["done"] is True


# ---------------------------------------------------------------------------
# Legacy open_items coercion (plain string array -> tasks)
# ---------------------------------------------------------------------------

class TestLegacyOpenItemsCoercion:
    def test_plain_string_array_is_coerced_to_open_tasks(self):
        client, session = _make_client()
        session.add(ProjectTopic(topic_id="legacy-1", title="Legacy", active=True))
        session.add(
            ProjectCondition(
                topic_id="legacy-1",
                summary="",
                open_items_json='["a","b"]',
            )
        )
        session.commit()

        response = client.get("/api/v1/project-conditions", headers=_auth())
        assert response.status_code == 200
        item = next(c for c in response.json()["data"] if c["topic_id"] == "legacy-1")
        assert item["open_items"] == [
            {"text": "a", "done": False},
            {"text": "b", "done": False},
        ]


# ---------------------------------------------------------------------------
# Log timeline
# ---------------------------------------------------------------------------

class TestProjectLogs:
    def _create(self, client: TestClient, topic_id: str) -> None:
        client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={"title": "Logged", "topic_id": topic_id, "open_items": []},
        )

    def test_add_log_grows_timeline_and_sets_last_activity(self):
        client, _ = _make_client()
        self._create(client, "logs-1")

        before = client.get("/api/v1/project-conditions", headers=_auth())
        cond_before = next(c for c in before.json()["data"] if c["topic_id"] == "logs-1")
        assert cond_before["logs"] == []
        assert cond_before["last_activity_at"] is None

        response = client.post(
            f"{_topic_path('logs-1')}/logs",
            headers=_auth(),
            json={"body": "first log entry"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["logs"]) == 1
        assert data["logs"][0]["body"] == "first log entry"
        assert data["last_activity_at"] is not None

    def test_delete_log_wrong_topic_404_right_topic_shrinks(self):
        client, _ = _make_client()
        self._create(client, "logs-2")
        self._create(client, "logs-other")

        add = client.post(
            f"{_topic_path('logs-2')}/logs",
            headers=_auth(),
            json={"body": "entry to delete"},
        )
        log_id = add.json()["data"]["logs"][0]["id"]

        # Wrong topic_id for this log -> 404.
        wrong = client.delete(
            f"{_topic_path('logs-other')}/logs/{log_id}",
            headers=_auth(),
        )
        assert wrong.status_code == 404

        # Right topic_id -> 200 and the timeline shrinks back to empty.
        right = client.delete(
            f"{_topic_path('logs-2')}/logs/{log_id}",
            headers=_auth(),
        )
        assert right.status_code == 200
        assert right.json()["data"]["logs"] == []


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

class TestArchiveProject:
    def test_archive_hides_from_board(self):
        client, _ = _make_client()
        client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={"title": "To Archive", "topic_id": "archive-1", "open_items": []},
        )
        assert any(
            c["topic_id"] == "archive-1"
            for c in client.get("/api/v1/project-conditions", headers=_auth()).json()["data"]
        )

        archived = client.patch(
            _topic_path("archive-1"),
            headers=_auth(),
            json={"active": False},
        )
        assert archived.status_code == 200
        assert archived.json()["data"]["active"] is False

        listing = client.get("/api/v1/project-conditions", headers=_auth())
        assert all(c["topic_id"] != "archive-1" for c in listing.json()["data"])


# ---------------------------------------------------------------------------
# Delete (and goal detachment)
# ---------------------------------------------------------------------------

class TestDeleteProject:
    def test_delete_detaches_referencing_goal(self):
        client, session = _make_client()
        client.post(
            "/api/v1/projects",
            headers=_auth(),
            json={"title": "Has Goal", "topic_id": "del-goal-1", "open_items": []},
        )
        session.add(Goal(slug="goal-on-del", title="Goal On Del", topic_id="del-goal-1"))
        session.commit()

        response = client.delete(_topic_path("del-goal-1"), headers=_auth())
        assert response.status_code == 200
        assert response.json()["data"]["topic_id"] == "del-goal-1"

        # The topic is gone and the goal's topic_id is detached to null (no FK error).
        session.expire_all()
        assert session.get(ProjectTopic, "del-goal-1") is None
        goal = session.query(Goal).filter(Goal.slug == "goal-on-del").one()
        assert goal.topic_id is None


# ---------------------------------------------------------------------------
# Unauthenticated (no token) -> 401 on every new endpoint
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    def test_post_create_without_token_returns_401(self):
        client, _ = _make_client()
        response = client.post("/api/v1/projects", json={"title": "x", "open_items": []})
        assert response.status_code == 401

    def test_patch_without_token_returns_401(self):
        client, _ = _make_client()
        response = client.patch(_topic_path("anything"), json={"title": "x"})
        assert response.status_code == 401

    def test_delete_without_token_returns_401(self):
        client, _ = _make_client()
        response = client.delete(_topic_path("anything"))
        assert response.status_code == 401

    def test_add_log_without_token_returns_401(self):
        client, _ = _make_client()
        response = client.post(f"{_topic_path('anything')}/logs", json={"body": "x"})
        assert response.status_code == 401

    def test_delete_log_without_token_returns_401(self):
        client, _ = _make_client()
        response = client.delete(f"{_topic_path('anything')}/logs/1")
        assert response.status_code == 401
