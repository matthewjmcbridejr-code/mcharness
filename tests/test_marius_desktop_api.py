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


def test_mcharness_agent_lanes_rich_detection_shape(monkeypatch):
    client = TestClient(app)
    # Force deterministic detection without host CLIs
    import src.marius_desktop.api as api_mod

    def fake_detect(name: str):
        if name == "codex":
            return {"installed": True, "executable_path": "/usr/local/bin/codex", "version": "codex version 0.42.0"}
        if name == "agy":
            return {"installed": False, "executable_path": None, "version": None}
        return {"installed": False, "executable_path": None, "version": None}

    monkeypatch.setattr(api_mod, "_detect_executable", fake_detect)
    r = client.get("/api/mcharness/agent-lanes")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "mcharness-control-plane"
    assert "lanes" in data and isinstance(data["lanes"], list) and len(data["lanes"]) >= 3
    by_id = { (l.get("id") or l.get("lane_id")): l for l in data["lanes"] }
    codex = by_id.get("codex_cli") or by_id.get("codex")
    assert codex is not None
    assert codex["installed"] is True
    assert codex.get("executable_path") == "/usr/local/bin/codex"
    assert "version" in codex
    assert codex.get("auth_status") in ("unknown", "likely_ready", "not_detected")
    assert codex.get("runner_mode") in ("dry_run_ready", "controlled_run_disabled", "manual")
    assert isinstance(codex.get("safety_notes"), list)
    assert "last_checked_at" in codex
    # legacy compat keys present
    assert codex.get("lane_id") == "codex_cli"
    assert "title" in codex
    manual = by_id.get("manual_paste")
    assert manual is not None
    assert manual.get("runner_mode") == "manual"
    assert manual.get("installed") is True


def test_mcharness_repos_enhanced_git_status():
    client = TestClient(app)
    r = client.get("/api/mcharness/repos")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "mcharness-control-plane"
    assert "repos" in data
    repos = { (x.get("repo_id") or x.get("label")): x for x in data["repos"] }
    # at least the export one exists in this tree
    exp = repos.get("mcharness-public-export")
    assert exp is not None
    assert exp.get("exists") is True
    assert "current_branch" in exp
    assert "dirty" in exp
    assert "changed_files_count" in exp
    assert "last_commit_short" in exp
    assert "status_summary" in exp
    assert isinstance(exp.get("safety_notes"), list)


def test_mcharness_runner_intent_dry_run_and_rejects(monkeypatch):
    client = TestClient(app)
    # create a minimal manual session for a valid session_id
    create = client.post(
        "/api/mcharness/sessions",
        json={
            "title": "runner-intent-test",
            "objective": "test dry run preview",
            "plan_instruction": "just a test",
            "repo_path": "/root/mcharness-public-export",
            "agent_lane": "manual_paste",
        },
    )
    assert create.status_code == 200, create.text
    sid = create.json()["session_id"]

    # happy dry_run with manual
    intent = client.post(
        f"/api/mcharness/sessions/{sid}/runner-intent",
        json={"lane_id": "manual_paste", "repo_id": "mcharness-public-export", "mode": "dry_run"},
    )
    assert intent.status_code == 200, intent.text
    d = intent.json()
    assert d["ok"] is True
    assert d["real_execution_enabled"] is False
    assert "command_preview" in d and "MANUAL" in d["command_preview"]
    assert "prompt_file_path" in d and sid in d["prompt_file_path"]
    assert "transcript_file_path" in d
    assert d["safety_policy"]["public_real_agent_launch_disabled"] is True
    assert d["safety_policy"]["arbitrary_shell_disabled"] is True

    # reject unknown lane
    bad_lane = client.post(f"/api/mcharness/sessions/{sid}/runner-intent", json={"lane_id": "no_such_lane", "repo_id": "mcharness-public-export", "mode": "dry_run"})
    assert bad_lane.status_code == 400

    # reject unknown repo
    bad_repo = client.post(f"/api/mcharness/sessions/{sid}/runner-intent", json={"lane_id": "manual_paste", "repo_id": "not-an-allowlisted-repo", "mode": "dry_run"})
    assert bad_repo.status_code == 400

    # reject non-dry
    bad_mode = client.post(f"/api/mcharness/sessions/{sid}/runner-intent", json={"lane_id": "manual_paste", "repo_id": "mcharness-public-export", "mode": "real"})
    assert bad_mode.status_code == 400

    # also works for a codex lane (even if not installed here) - preview does not require installed
    codex_intent = client.post(f"/api/mcharness/sessions/{sid}/runner-intent", json={"lane_id": "codex_cli", "repo_id": "mcharness-public-export", "mode": "dry_run"})
    assert codex_intent.status_code == 200
    cd = codex_intent.json()
    assert cd["real_execution_enabled"] is False


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
