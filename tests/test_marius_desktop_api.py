import shutil

import pytest
from fastapi.testclient import TestClient

from src.marius_desktop.captain import CAPTAIN_ROOT
from src.marius_desktop.graph import CHECKPOINT_DB_PATH, MCTABLE_ROOT, TASKS_DIR
from src.server.api import app


@pytest.fixture(autouse=True)
def clean_mctable():
    for d in [TASKS_DIR, MCTABLE_ROOT / "worker_runs", MCTABLE_ROOT / "checkpoints", CAPTAIN_ROOT]:
        if d.exists():
            shutil.rmtree(d)
    yield
    for d in [TASKS_DIR, MCTABLE_ROOT / "worker_runs", MCTABLE_ROOT / "checkpoints", CAPTAIN_ROOT]:
        if d.exists():
            shutil.rmtree(d)


def test_capabilities_endpoint():
    client = TestClient(app)
    response = client.get("/api/marius/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    langgraph_cap = next(item for item in data if item["name"] == "langgraph")
    sqlite_cap = next(item for item in data if item["name"] == "sqlite_checkpointing")
    assert langgraph_cap["status"] == "available"
    assert sqlite_cap["status"] == "available"
    assert "checkpointing" in langgraph_cap["summary"].lower()


def test_status_endpoint():
    client = TestClient(app)
    response = client.get("/api/marius/status")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "marius-desktop-api"
    assert data["status"] == "online"
    assert data["langgraph_available"] is True
    assert data["sqlite_checkpointing_available"] is True
    assert data["checkpoint_db_path"].endswith("marius_desktop.sqlite")
    assert isinstance(data["checkpoint_exists"], bool)


def test_mcharness_health_endpoint_reports_public_manual_mode():
    client = TestClient(app)
    response = client.get("/api/mcharness/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["service"] == "mcharness-control-plane"
    assert data["mode"] == "public_manual"
    assert data["real_agent_launch_enabled"] is False
    assert data["arbitrary_command_execution_enabled"] is False
    assert isinstance(data["commit"], str) and len(data["commit"]) == 40
    assert data["available_lanes_count"] >= 1
    assert data["repo_count"] >= 1


def test_public_write_guard_blocks_worker_routes_when_disabled(monkeypatch):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "false")
    monkeypatch.delenv("MCHARNESS_ADMIN_TOKEN", raising=False)
    client = TestClient(app)

    dangerous = client.post(
        "/api/marius/tasks",
        json={
            "task_id": "guarded-task",
            "title": "Guarded Task",
            "description": "Should be blocked when public writes are off",
            "command": "fake-worker-success",
            "args": [],
        },
    )
    assert dangerous.status_code == 403
    assert "disabled" in dangerous.json()["detail"].lower()

    manual = client.post(
        "/api/mcharness/sessions",
        json={
            "title": "Manual cockpit session",
            "objective": "Manual cockpit writes remain available.",
            "plan_instruction": "Create a bounded manual queue.",
            "repo_path": "/root/mcharness-public-export",
            "agent_lane": "manual_paste",
        },
    )
    assert manual.status_code == 200


def test_create_task_validation():
    client = TestClient(app)

    bad_payload = {
        "task_id": "bad-task",
        "title": "Bad Task",
        "description": "Unknown command",
        "command": "rm -rf /",
        "args": [],
    }
    response = client.post("/api/marius/tasks", json=bad_payload)
    assert response.status_code == 400
    assert "not allowlisted" in response.json()["detail"]

    bad_id_payload = {
        "task_id": "bad/id/here",
        "title": "Bad ID",
        "description": "Slash in ID",
        "command": "fake-worker-success",
        "args": [],
    }
    response = client.post("/api/marius/tasks", json=bad_id_payload)
    assert response.status_code == 422

    good_payload = {
        "task_id": "good-task",
        "title": "Good Task",
        "description": "Success task",
        "command": "fake-worker-success",
        "args": [],
    }
    response = client.post("/api/marius/tasks", json=good_payload)
    assert response.status_code == 200
    task_data = response.json()
    assert task_data["task_id"] == "good-task"
    assert task_data["current_step"] == "human_review_gate"
    assert task_data["status"] == "paused"
    assert task_data["proof_status"] == "needs_review"
    assert CHECKPOINT_DB_PATH.exists()


def test_get_task_not_found():
    client = TestClient(app)
    response = client.get("/api/marius/tasks/non-existent-task-id")
    assert response.status_code == 404


def test_get_tasks_is_read_only():
    client = TestClient(app)
    payload = {
        "task_id": "task-readonly",
        "title": "Read Only Task",
        "description": "Read-only GET verification",
        "command": "fake-worker-success",
        "args": [],
    }
    created = client.post("/api/marius/tasks", json=payload)
    assert created.status_code == 200
    before = created.json()

    response = client.get("/api/marius/tasks")
    assert response.status_code == 200
    tasks = response.json()
    task = next(item for item in tasks if item["task_id"] == "task-readonly")
    assert task["status"] == before["status"]
    assert task["current_step"] == before["current_step"]
    assert task["worker_run_id"] == before["worker_run_id"]

    task_response = client.get("/api/marius/tasks/task-readonly")
    assert task_response.status_code == 200
    assert task_response.json()["current_step"] == before["current_step"]


def test_post_task_decision():
    client = TestClient(app)
    good_payload = {
        "task_id": "task-for-decision",
        "title": "Decision Task",
        "description": "Success task",
        "command": "fake-worker-success",
        "args": [],
    }
    client.post("/api/marius/tasks", json=good_payload)

    response = client.post(
        "/api/marius/tasks/task-for-decision/decision",
        json={"decision": "invalid", "actor": "operator"},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/marius/tasks/task-for-decision/decision",
        json={"decision": "approve", "actor": "operator", "reviewer_note": "Approved"},
    )
    assert response.status_code == 200
    task_data = response.json()
    assert task_data["status"] == "completed"
    assert task_data["proof_status"] == "approved"
    assert task_data["current_step"] == "complete"


def test_worker_run_and_logs():
    client = TestClient(app)
    payload = {
        "task_id": "task-worker-check",
        "title": "Worker Task",
        "description": "Sleep task",
        "command": "fake-worker-success",
        "args": [],
    }
    res = client.post("/api/marius/tasks", json=payload)
    run_id = res.json()["worker_run_id"]
    assert run_id is not None

    response = client.get(f"/api/marius/worker-runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["run_id"] == run_id

    response = client.get(f"/api/marius/worker-runs/{run_id}/logs")
    assert response.status_code == 200
    assert "Starting fake success worker" in response.json()["logs"]


def test_captain_template_routes_exposed_via_api():
    client = TestClient(app)

    templates_response = client.get("/api/marius/captain/templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    assert any(item["template_id"] == "release_qa" for item in templates)

    template_response = client.get("/api/marius/captain/templates/release_qa")
    assert template_response.status_code == 200
    template = template_response.json()

    create_response = client.post(
        "/api/marius/captain/runs/from-template",
        json={"template": template, "next_action": "inspect"},
    )
    assert create_response.status_code == 200
    run = create_response.json()
    assert run["prompt_queue"]
    assert run["hard_gates"]


def test_captain_manual_evidence_and_gate_decision_routes_exposed_via_api():
    client = TestClient(app)
    created = client.post("/api/marius/captain/runs", json={"objective": "Manual evidence API", "next_action": "inspect"})
    run_id = created.json()["run_id"]

    evidence_response = client.post(
        f"/api/marius/captain/runs/{run_id}/evidence",
        json={
            "kind": "manual_observation",
            "summary": "API proof",
            "status": "recorded",
            "command_text": "python -m pytest -q tests/test_marius_desktop_api.py",
            "captured_by": "operator",
            "artifacts": [],
        },
    )
    assert evidence_response.status_code == 200
    assert evidence_response.json()["evidence_records"][0]["kind"] == "manual_observation"

    gate_response = client.post(
        f"/api/marius/captain/runs/{run_id}/gate",
        json={"kind": "manual_review", "reason": "API proof gate", "triggered_by": "operator"},
    )
    assert gate_response.status_code == 200
    gate_id = gate_response.json()["hard_gates"][0]["gate_id"]

    decision_response = client.post(
        f"/api/marius/captain/runs/{run_id}/gates/{gate_id}/decision",
        json={"decision": "reject", "actor": "operator", "reviewer_note": "Recorded through API"},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["hard_gates"][0]["decision"] == "reject"
