import json

from backend.app.hq.models import Severity, TaskStatus
from backend.app.hq.adapters.sigmacontrol import SigmaControlAdapter


def test_missing_state_is_unhealthy_and_empty(tmp_path) -> None:
    a = SigmaControlAdapter(str(tmp_path / "nope.json"))
    assert a.healthy() is False
    snap = a.fetch_snapshot()
    assert snap.healthy is False
    assert snap.source == "sigmacontrol"
    assert snap.projects == [] and snap.tasks == [] and snap.blockers == []


def test_projects_tasks_blockers_map_and_scrub(tmp_path) -> None:
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "projects": [
                    {"id": "nets", "name": "NETS", "slug": "nets", "owner": "leo",
                     "status": "active", "updated_at": "2026-06-23T09:00:00", "secret": "ZZSECRETZZ"}
                ],
                "tasks": [
                    {"id": "t1", "title": "Ship HQ", "project": "nets", "status": "in_progress",
                     "priority": 1, "password": "ZZPASSZZ"}
                ],
                "blockers": [
                    {"id": "b1", "title": "DB lock", "severity": "critical",
                     "entity_type": "task", "entity_id": "t1", "owner": "leo"}
                ],
            }
        )
    )
    snap = SigmaControlAdapter(str(p)).fetch_snapshot()
    assert snap.healthy is True

    assert len(snap.projects) == 1
    proj = snap.projects[0]
    assert proj.source == "sigmacontrol" and proj.id == "sigmacontrol:nets"
    assert proj.name == "NETS" and proj.owner == "leo"

    task = snap.tasks[0]
    assert task.id == "sigmacontrol:t1"
    assert task.status == TaskStatus.in_progress
    assert task.project_id == "sigmacontrol:nets"

    blk = snap.blockers[0]
    assert blk.severity == Severity.critical
    assert blk.entity_id == "sigmacontrol:t1"

    dump = json.dumps(snap.model_dump(), default=str)
    assert "ZZSECRETZZ" not in dump
    assert "ZZPASSZZ" not in dump


def test_unknown_enums_fall_back(tmp_path) -> None:
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "tasks": [{"id": "t9", "title": "x", "status": "zzz"}],
                "blockers": [{"id": "b9", "title": "y", "severity": "zzz"}],
            }
        )
    )
    snap = SigmaControlAdapter(str(p)).fetch_snapshot()
    assert snap.tasks[0].status == TaskStatus.todo
    assert snap.blockers[0].severity == Severity.medium


def test_malformed_json_is_unhealthy(tmp_path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("nope")
    assert SigmaControlAdapter(str(p)).healthy() is False
