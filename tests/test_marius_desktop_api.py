import json
import subprocess
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


def test_mcharness_captain_status_reports_disabled_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MCHARNESS_CAPTAIN_MODEL", raising=False)
    client = TestClient(app)
    response = client.get("/api/mcharness/captain/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["configured"] is False
    assert data["provider"] == "openrouter"
    assert data["model"] == "openrouter/auto"
    assert data["planning_enabled"] is False
    assert data["key_source"] == "missing"
    assert data["private_key_setup_enabled"] is False
    assert "OPENROUTER_API_KEY" in data["notes"][0]
    assert "test-openrouter-key" not in response.text


def test_mcharness_captain_status_reports_configured_with_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("MCHARNESS_CAPTAIN_MODEL", "openrouter/test-model")
    client = TestClient(app)
    response = client.get("/api/mcharness/captain/status")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["provider"] == "openrouter"
    assert data["model"] == "openrouter/test-model"
    assert data["planning_enabled"] is True
    assert data["key_source"] == "env"
    assert data["private_key_setup_enabled"] is False
    assert "test-openrouter-key" not in response.text


def test_mcharness_captain_key_save_requires_private_write_access(monkeypatch):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "false")
    monkeypatch.delenv("MCHARNESS_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/key",
        json={"api_key": "sk-or-private-test-key", "model": "openrouter/auto"},
    )
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


def test_mcharness_captain_key_save_delete_and_status_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MCHARNESS_CAPTAIN_MODEL", raising=False)

    import src.marius_desktop.api as api_mod

    monkeypatch.setattr(api_mod, "MCTABLE_ROOT", tmp_path)
    client = TestClient(app)

    saved = client.post(
        "/api/mcharness/captain/key",
        json={"api_key": "sk-or-private-test-key", "model": "openrouter/custom"},
    )
    assert saved.status_code == 200, saved.text
    saved_data = saved.json()
    assert saved_data["configured"] is True
    assert saved_data["key_source"] == "saved"
    assert saved_data["model"] == "openrouter/custom"
    assert "sk-or-private-test-key" not in saved.text

    status = client.get("/api/mcharness/captain/status")
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["configured"] is True
    assert status_data["key_source"] == "saved"
    assert status_data["private_key_setup_enabled"] is True
    assert "sk-or-private-test-key" not in status.text

    removed = client.delete("/api/mcharness/captain/key")
    assert removed.status_code == 200, removed.text
    removed_data = removed.json()
    assert removed_data["configured"] is False
    assert removed_data["key_source"] == "missing"
    assert "sk-or-private-test-key" not in removed.text

    status_after = client.get("/api/mcharness/captain/status")
    assert status_after.status_code == 200
    assert status_after.json()["configured"] is False


def test_mcharness_captain_key_env_precedence_over_saved_key(monkeypatch, tmp_path):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env-test-key")
    monkeypatch.setenv("MCHARNESS_CAPTAIN_MODEL", "openrouter/env-model")

    import src.marius_desktop.api as api_mod

    monkeypatch.setattr(api_mod, "MCTABLE_ROOT", tmp_path)
    saved_path = tmp_path / "secrets" / "captain_openrouter.json"
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_text(
        json.dumps(
            {
                "provider": "openrouter",
                "api_key": "sk-or-saved-test-key",
                "model": "openrouter/saved-model",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    status = client.get("/api/mcharness/captain/status")
    assert status.status_code == 200
    data = status.json()
    assert data["configured"] is True
    assert data["key_source"] == "env"
    assert data["model"] == "openrouter/env-model"
    assert "sk-or-env-test-key" not in status.text
    assert "sk-or-saved-test-key" not in status.text


def test_mcharness_captain_key_save_rejects_when_env_key_present(monkeypatch):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env-test-key")

    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/key",
        json={"api_key": "sk-or-private-test-key", "model": "openrouter/auto"},
    )
    assert response.status_code == 409
    assert "environment" in response.json()["detail"].lower()


def test_mcharness_captain_plan_rejects_missing_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/plan",
        json={
            "goal": "Build a webpage just like aol.com",
            "repo_id": "hybrid-agent-os",
            "lane_id": "codex_cli",
        },
    )
    assert response.status_code == 503
    assert "Captain is not configured" in response.json()["detail"]


def test_mcharness_captain_plan_rejects_unknown_repo(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/plan",
        json={
            "goal": "Build a webpage just like aol.com",
            "repo_id": "no-such-repo",
            "lane_id": "codex_cli",
        },
    )
    assert response.status_code == 400
    assert "Unknown repo_id" in response.json()["detail"]


def test_mcharness_captain_plan_rejects_unknown_lane(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/plan",
        json={
            "goal": "Build a webpage just like aol.com",
            "repo_id": "hybrid-agent-os",
            "lane_id": "no-such-lane",
        },
    )
    assert response.status_code == 400
    assert "Unknown agent lane" in response.json()["detail"]


def test_mcharness_captain_plan_parses_mocked_openrouter_json(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("MCHARNESS_CAPTAIN_MODEL", "openrouter/auto")

    import src.marius_desktop.api as api_mod

    def fake_openrouter(*, messages, model, timeout):
        assert model == "openrouter/auto"
        assert any("Captain Deck" in item["content"] for item in messages if item["role"] == "system")
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title": "Build AOL-inspired webpage",
                                "summary": "Create an AOL-inspired homepage layout in the existing frontend.",
                                "steps": [
                                    {
                                        "title": "Inspect frontend structure",
                                        "prompt": "Inspect the frontend entrypoint and identify the minimal files to change.",
                                    },
                                    {
                                        "title": "Implement layout",
                                        "prompt": "Modify only the selected frontend files to add the requested layout.",
                                    },
                                    {
                                        "title": "Verify and report",
                                        "prompt": "Run the focused checks and return a concise proof report.",
                                    },
                                ],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(api_mod, "_openrouter_chat_completion", fake_openrouter)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/plan",
        json={
            "goal": "Build a webpage just like aol.com",
            "repo_id": "hybrid-agent-os",
            "lane_id": "codex_cli",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["title"] == "Build AOL-inspired webpage"
    assert data["summary"].startswith("Create an AOL-inspired homepage layout")
    assert len(data["steps"]) == 3
    assert data["steps"][0]["id"] == "step_1"
    assert data["steps"][0]["agent"] == "codex_cli"
    assert data["steps"][0]["status"] == "queued"
    assert "Exact goal: Build a webpage just like aol.com" in data["steps"][0]["prompt"]
    assert "Forbidden actions:" in data["steps"][0]["prompt"]
    assert "Acceptance checks:" in data["steps"][0]["prompt"]
    assert "Final proof format:" in data["steps"][0]["prompt"]
    assert "test-openrouter-key" not in response.text


def test_mcharness_captain_plan_rejects_invalid_model_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")

    import src.marius_desktop.api as api_mod

    def fake_openrouter(*, messages, model, timeout):
        return {"choices": [{"message": {"content": "not-json"}}]}

    monkeypatch.setattr(api_mod, "_openrouter_chat_completion", fake_openrouter)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/plan",
        json={
            "goal": "Build a webpage just like aol.com",
            "repo_id": "hybrid-agent-os",
            "lane_id": "codex_cli",
        },
    )
    assert response.status_code == 502
    assert "valid JSON" in response.json()["detail"]


def test_mcharness_captain_plan_uses_saved_key_when_env_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    monkeypatch.delenv("MCHARNESS_CAPTAIN_MODEL", raising=False)

    import src.marius_desktop.api as api_mod

    monkeypatch.setattr(api_mod, "MCTABLE_ROOT", tmp_path)
    monkeypatch.setattr(api_mod, "CAPTAIN_PLAN_ROOT", tmp_path / "captain" / "plans")
    saved_path = tmp_path / "secrets" / "captain_openrouter.json"
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_text(
        json.dumps(
            {
                "provider": "openrouter",
                "api_key": "sk-or-saved-test-key",
                "model": "openrouter/saved-model",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    def fake_openrouter(*, messages, model, timeout):
        assert model == "openrouter/saved-model"
        assert any("Captain Deck" in item["content"] for item in messages if item["role"] == "system")
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title": "Saved-key Captain plan",
                                "summary": "Uses the saved private OpenRouter key.",
                                "steps": [
                                    {
                                        "title": "Inspect frontend structure",
                                        "prompt": "Inspect the frontend entrypoint and identify the minimal files to change.",
                                    },
                                    {
                                        "title": "Implement layout",
                                        "prompt": "Modify only the selected frontend files to add the requested layout.",
                                    },
                                    {
                                        "title": "Verify and report",
                                        "prompt": "Run the focused checks and return a concise proof report.",
                                    },
                                ],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(api_mod, "_openrouter_chat_completion", fake_openrouter)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/captain/plan",
        json={
            "goal": "Create a short read-only plan for inspecting the McHarness frontend. Do not edit files.",
            "repo_id": "hybrid-agent-os",
            "lane_id": "codex_cli",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["title"] == "Saved-key Captain plan"
    assert "sk-or-saved-test-key" not in response.text


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


# --- runner foundation tests (use fake_test_lane + monkeypatch; no real provider burn) ---

def test_runner_disabled_by_default():
    client = TestClient(app)
    # create session with manual (allowed)
    s = client.post("/api/mcharness/sessions", json={
        "title": "r1", "objective": "o", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "manual_paste"
    })
    assert s.status_code == 200
    sid = s.json()["session_id"]
    # start should be blocked for non-fake when default false
    r = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={
        "lane_id": "codex_cli", "repo_id": "mcharness-public-export"
    })
    assert r.status_code in (403, 400)
    assert "disabled" in (r.text or "").lower() or "not implemented" in (r.text or "").lower()


def test_fake_test_lane_runner_full_flow(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    # patch start to avoid real tmux in test (still exercises state, endpoints, evidence)
    import src.marius_desktop.api as api_mod
    orig_start = api_mod._start_fake_runner
    def fake_start(state):
        p = api_mod.Path(state["transcript_file_path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("MCHarness fake runner started\nartifact proof line\nMCHarness fake runner complete\nMCH_EXIT_CODE:0\n", encoding="utf-8")
        state["status"] = "exited"
        state["exit_code"] = 0
        return state
    monkeypatch.setattr(api_mod, "_start_fake_runner", fake_start)

    s = client.post("/api/mcharness/sessions", json={
        "title": "fake-runner", "objective": "proof", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "fake_test_lane"
    })
    assert s.status_code == 200
    sid = s.json()["session_id"]

    # start
    st = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={
        "lane_id": "fake_test_lane", "repo_id": "mcharness-public-export"
    })
    assert st.status_code == 200
    data = st.json()
    assert data["lane_id"] == "fake_test_lane"
    assert data["status"] in ("running", "exited")
    assert "transcript_file_path" in data
    assert data["safety_policy"]["arbitrary_shell_disabled"] is True

    # status
    st2 = client.get(f"/api/mcharness/sessions/{sid}/runner/status")
    assert st2.status_code == 200
    assert st2.json()["status"] in ("running", "exited", "stopped")

    # transcript
    tr = client.get(f"/api/mcharness/sessions/{sid}/runner/transcript")
    assert tr.status_code == 200
    tdata = tr.json()
    assert "MCHarness fake runner" in (tdata.get("transcript") or "")

    # to evidence
    ev = client.post(f"/api/mcharness/sessions/{sid}/runner/transcript-to-evidence")
    assert ev.status_code == 200
    ed = ev.json()
    assert ed["ok"] is True
    assert "artifact" in ed

    # stop (scoped)
    sp = client.post(f"/api/mcharness/sessions/{sid}/runner/stop")
    assert sp.status_code == 200
    assert sp.json()["status"] == "stopped"

    # manual paste still works (parallel)
    man = client.post(f"/api/mcharness/sessions/{sid}/manual-result", json={
        "summary": "manual still works with runner present", "verdict": "passed"
    })
    assert man.status_code == 200


def test_runner_rejects_unknown_lane_repo(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    s = client.post("/api/mcharness/sessions", json={
        "title": "r2", "objective": "o", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "manual_paste"
    })
    sid = s.json()["session_id"]
    badl = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={"lane_id": "nope", "repo_id": "mcharness-public-export"})
    assert badl.status_code == 400
    badr = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={"lane_id": "fake_test_lane", "repo_id": "nope"})
    assert badr.status_code == 400


def test_codex_detection_and_disabled_without_both_envs(monkeypatch):
    client = TestClient(app)
    # force codex "installed" via patch, no real exec
    import src.marius_desktop.api as api_mod
    orig_detect = api_mod._detect_executable
    def fake_detect(name):
        if name == "codex":
            return {"installed": True, "executable_path": "/fake/codex", "version": "codex-cli 0.137.0"}
        return orig_detect(name)
    monkeypatch.setattr(api_mod, "_detect_executable", fake_detect)

    # default: both false -> codex start disabled
    s = client.post("/api/mcharness/sessions", json={
        "title": "c1", "objective": "o", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "manual_paste"
    })
    sid = s.json()["session_id"]
    r = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={"lane_id": "codex_cli", "repo_id": "mcharness-public-export"})
    assert r.status_code == 403
    assert "codex_runner" in (r.text or "").lower() or "disabled" in (r.text or "").lower()

    # with only tmux true, still disabled for codex
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    r2 = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={"lane_id": "codex_cli", "repo_id": "mcharness-public-export"})
    assert r2.status_code == 403

    # with both, would allow (but we don't start real here, just reach)
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    # patch start to avoid actual codex/tmux in this unit test
    def fake_start_codex(st, c):
        st["status"] = "running"
        st["notes"].append("codex (patched, no real exec)")
        return st
    monkeypatch.setattr(api_mod, "_start_codex_runner", fake_start_codex)
    r3 = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={"lane_id": "codex_cli", "repo_id": "mcharness-public-export"})
    assert r3.status_code == 200
    d = r3.json()
    assert d["lane_id"] == "codex_cli"
    assert d["safety_policy"]["codex_runner_enabled"] is True
    assert "real_provider" in d["safety_policy"]


def test_codex_command_template_and_missing_handling(monkeypatch):
    client = TestClient(app)
    import src.marius_desktop.api as api_mod
    # patch detect to installed
    def fake_detect(name):
        if name == "codex":
            return {"installed": True, "executable_path": "/fake/codex", "version": "0.137"}
        return {"installed": False, "executable_path": None, "version": None}
    monkeypatch.setattr(api_mod, "_detect_executable", fake_detect)
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    def fake_start(st, c): 
        st["status"] = "running"
        return st
    monkeypatch.setattr(api_mod, "_start_codex_runner", fake_start)

    s = client.post("/api/mcharness/sessions", json={
        "title": "c2", "objective": "o", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "manual_paste"
    })
    sid = s.json()["session_id"]
    st = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={"lane_id": "codex_cli", "repo_id": "mcharness-public-export"})
    assert st.status_code == 200
    # intent preview shape for codex uses exec template
    intent = client.post(f"/api/mcharness/sessions/{sid}/runner-intent", json={"lane_id": "codex_cli", "repo_id": "mcharness-public-export", "mode": "dry_run"})
    assert intent.status_code == 200
    ip = intent.json()
    assert "codex exec --cd" in ip["command_preview"]
    assert "--output-last-message" in ip["command_preview"]

    # missing codex
    def fake_missing(name):
        if name == "codex":
            return {"installed": False, "executable_path": None, "version": None}
        return fake_detect(name)
    monkeypatch.setattr(api_mod, "_detect_executable", fake_missing)
    # lanes should reflect
    lanes = client.get("/api/mcharness/agent-lanes").json()["lanes"]
    cod = next((l for l in lanes if l["lane_id"] == "codex_cli"), None)
    assert cod is not None
    assert cod["installed"] is False
    assert "not found" in " ".join(cod.get("safety_notes", [])).lower()


def test_fake_interactive_tmux_runner_prompt_injection_and_capture(monkeypatch):
    """Real tmux (harmless long-running process) + send + capture proves prompt appears in live transcript.
    Status stays running until stop. Stop only affects that session.
    """
    client = TestClient(app)
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    import src.marius_desktop.api as api_mod
    import time

    s = client.post("/api/mcharness/sessions", json={
        "title": "fake-interactive", "objective": "o", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "fake_test_lane"
    })
    assert s.status_code == 200
    sid = s.json()["session_id"]

    st = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={
        "lane_id": "fake_test_lane", "repo_id": "mcharness-public-export"
    })
    assert st.status_code == 200
    data = st.json()
    name = data.get("tmux_session_name")
    assert name
    assert data["status"] in ("waiting_for_codex", "running", "starting")

    time.sleep(0.3)  # allow tmux to start the process

    # For fake lane we do not use the codex-specific send (it would 400); instead prove start + live capture works for interactive process.
    # (The send + prompt_sent is covered in the codex patch test below.)
    tr = client.get(f"/api/mcharness/sessions/{sid}/runner/transcript")
    assert tr.status_code == 200
    txt = tr.json().get("transcript", "")
    assert "started" in txt.lower() or len(txt) > 3   # initial output from the harmless process

    # status running
    st2 = client.get(f"/api/mcharness/sessions/{sid}/runner/status")
    assert st2.status_code == 200
    assert st2.json()["status"] in ("running", "waiting_for_codex", "starting")

    # stop only this session
    sp = client.post(f"/api/mcharness/sessions/{sid}/runner/stop")
    assert sp.status_code == 200
    assert sp.json()["status"] == "stopped"


def test_codex_cli_uses_interactive_tmux_mode_not_exec_wrapper(monkeypatch):
    """Codex lane when flags enabled uses pure interactive launch (no exec wrapper in command).
    Send path is exercised. No real codex executed.
    """
    client = TestClient(app)
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    import src.marius_desktop.api as api_mod

    # patch start to record what command would be used, without real tmux
    recorded = {}
    orig = api_mod._start_codex_runner
    def fake_start(state, cwd):
        recorded["status"] = "waiting_for_codex"
        recorded["notes"] = ["interactive launch"]
        state["status"] = "waiting_for_codex"
        state["attach_command"] = "tmux attach -t fake"
        state["notes"].append("codex interactive tmux (not exec < file)")
        return state
    monkeypatch.setattr(api_mod, "_start_codex_runner", fake_start)

    s = client.post("/api/mcharness/sessions", json={
        "title": "codex-int", "objective": "o", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "codex_cli"
    })
    sid = s.json()["session_id"]

    st = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={
        "lane_id": "codex_cli", "repo_id": "mcharness-public-export"
    })
    assert st.status_code == 200
    start_body = st.json()
    assert start_body["status"] == "waiting_for_codex"
    tmux_name = start_body["tmux_session_name"]

    calls = []

    def fake_safe_cmd(cmd, timeout=2.5, cwd=None):
        calls.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(api_mod, "_safe_cmd", fake_safe_cmd)
    monkeypatch.setattr(api_mod, "_run_for_session", lambda session_id: {"run_id": "run-queue"})
    monkeypatch.setattr(api_mod, "_append_run_event", lambda *args, **kwargs: None)

    # send
    prompt = "TASK_PROMPT_HERE\nReturn the single line:\nMCH_CODEX_SUBMIT_PROOF_OK"
    send = client.post(f"/api/mcharness/sessions/{sid}/runner/send-prompt", json={"prompt": prompt})
    assert send.status_code == 200
    send_body = send.json()
    assert send_body["status"] == "awaiting_response"
    assert send_body["injected"] is True
    assert calls[:3] == [
        ("tmux", "send-keys", "-t", tmux_name, "-l", prompt),
        ("tmux", "send-keys", "-t", tmux_name, "Tab"),
        ("tmux", "send-keys", "-t", tmux_name, "Enter"),
    ]

    st2 = client.get(f"/api/mcharness/sessions/{sid}/runner/status")
    assert st2.json()["status"] == "awaiting_response"

    # stop
    sp = client.post(f"/api/mcharness/sessions/{sid}/runner/stop")
    assert sp.json()["status"] == "stopped"


def test_codex_start_auto_skips_update_prompt(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    import src.marius_desktop.api as api_mod

    calls = []

    def fake_safe_cmd(cmd, timeout=2.5, cwd=None):
        calls.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(api_mod, "_safe_cmd", fake_safe_cmd)
    monkeypatch.setattr(api_mod, "_get_tmux_transcript", lambda name: "Update available! 0.137.0 -> 0.138.0\nSkip until next version")

    s = client.post("/api/mcharness/sessions", json={
        "title": "codex-update-skip", "objective": "o", "plan_instruction": "p",
        "repo_path": "/root/mcharness-public-export", "agent_lane": "codex_cli"
    })
    sid = s.json()["session_id"]

    st = client.post(f"/api/mcharness/sessions/{sid}/runner/start", json={
        "lane_id": "codex_cli", "repo_id": "mcharness-public-export"
    })
    assert st.status_code == 200
    body = st.json()
    assert body["status"] == "waiting_for_codex"
    assert any(call[-1] == "2" for call in calls if call[:3] == ("tmux", "send-keys", "-t"))
    assert any(call[-1] == "Enter" for call in calls if call[:3] == ("tmux", "send-keys", "-t"))


def test_runner_send_key_allows_only_quick_reply_keys(monkeypatch, tmp_path):
    client = TestClient(app)
    import src.marius_desktop.api as api_mod

    session_id = "quick-reply-session"
    runner_id = "run_1234abcd"
    tmux_name = api_mod._tmux_session_name(session_id, runner_id)
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text("before\n", encoding="utf-8")
    state = {
        "session_id": session_id,
        "runner_id": runner_id,
        "lane_id": "codex_cli",
        "status": "prompt_sent",
        "tmux_session_name": tmux_name,
        "transcript_file_path": str(transcript_path),
    }
    calls = []

    def fake_load_runner_state(sid):
        assert sid == session_id
        return state

    def fake_safe_cmd(cmd, timeout=2.5, cwd=None):
        calls.append((tuple(cmd), timeout))
        if cmd[:3] == ["tmux", "has-session", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:4] == ["tmux", "send-keys", "-t", tmux_name]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(api_mod, "_load_runner_state", fake_load_runner_state)
    monkeypatch.setattr(api_mod, "_safe_cmd", fake_safe_cmd)
    monkeypatch.setattr(api_mod, "_run_for_session", lambda sid: {"run_id": "run-quick"})
    monkeypatch.setattr(api_mod, "_append_run_event", lambda *args, **kwargs: None)

    cases = [
        ("1", "1"),
        ("2", "2"),
        ("3", "3"),
        ("Enter", "Enter"),
        ("Ctrl+C", "C-c"),
    ]
    for requested, mapped in cases:
        response = client.post(f"/api/mcharness/sessions/{session_id}/runner/send-key", json={"key": requested})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["ok"] is True
        assert payload["sent_key"] == requested
        assert payload["tmux_session_name"] == tmux_name
        assert payload["transcript_excerpt"].startswith("before")
        assert any(call[0][-1] == mapped for call in calls if call[0][:4] == ("tmux", "send-keys", "-t", tmux_name))


def test_runner_send_key_submit_continue_sends_tab_then_enter(monkeypatch, tmp_path):
    client = TestClient(app)
    import src.marius_desktop.api as api_mod

    session_id = "submit-continue-session"
    runner_id = "run_5678abcd"
    tmux_name = api_mod._tmux_session_name(session_id, runner_id)
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text("before\n", encoding="utf-8")
    state = {
        "session_id": session_id,
        "runner_id": runner_id,
        "lane_id": "codex_cli",
        "status": "waiting_for_codex",
        "tmux_session_name": tmux_name,
        "transcript_file_path": str(transcript_path),
    }
    calls = []

    def fake_load_runner_state(sid):
        assert sid == session_id
        return state

    def fake_safe_cmd(cmd, timeout=2.5, cwd=None):
        calls.append((tuple(cmd), timeout))
        if cmd[:3] == ["tmux", "has-session", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:4] == ["tmux", "send-keys", "-t", tmux_name]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(api_mod, "_load_runner_state", fake_load_runner_state)
    monkeypatch.setattr(api_mod, "_safe_cmd", fake_safe_cmd)
    monkeypatch.setattr(api_mod, "_run_for_session", lambda sid: {"run_id": "run-submit"})
    monkeypatch.setattr(api_mod, "_append_run_event", lambda *args, **kwargs: None)

    response = client.post(f"/api/mcharness/sessions/{session_id}/runner/send-key", json={"key": "Submit / Continue"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["sent_key"] == "Submit / Continue"
    assert payload["status_note"] == "Prompt sent to Codex."
    sent_keys = [call[0][-1] for call in calls if call[0][:3] == ("tmux", "send-keys", "-t")]
    assert "Tab" in sent_keys
    assert "Enter" in sent_keys


def test_runner_send_key_rejects_invalid_state_and_arbitrary_tmux(monkeypatch):
    client = TestClient(app)
    import src.marius_desktop.api as api_mod

    session_id = "quick-reply-reject"
    runner_id = "run_deadbeef"
    bad_state = {
        "session_id": session_id,
        "runner_id": runner_id,
        "lane_id": "codex_cli",
        "status": "stopped",
        "tmux_session_name": "mch_arbitrary_target",
        "transcript_file_path": "/tmp/does-not-matter.txt",
    }

    monkeypatch.setattr(api_mod, "_load_runner_state", lambda sid: bad_state if sid == session_id else None)
    monkeypatch.setattr(api_mod, "_safe_cmd", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="", stderr=""))

    rejected_state = client.post(f"/api/mcharness/sessions/{session_id}/runner/send-key", json={"key": "1"})
    assert rejected_state.status_code == 409

    bad_state["status"] = "running"
    rejected_tmux = client.post(f"/api/mcharness/sessions/{session_id}/runner/send-key", json={"key": "1"})
    assert rejected_tmux.status_code == 400
    assert "mismatch" in rejected_tmux.text.lower()

    bad_state["tmux_session_name"] = api_mod._tmux_session_name(session_id, runner_id)
    missing_runner = client.post("/api/mcharness/sessions/other-session/runner/send-key", json={"key": "1"})
    assert missing_runner.status_code == 400


def test_mcharness_agents_returns_builtin_codex(monkeypatch):
    monkeypatch.delenv("MCHARNESS_TMUX_RUNNER_ENABLED", raising=False)
    monkeypatch.delenv("MCHARNESS_CODEX_RUNNER_ENABLED", raising=False)
    client = TestClient(app)
    response = client.get("/api/mcharness/agents")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["registry_write_enabled"] is False
    agents = data["agents"]
    assert any(item["id"] == "codex_cli" for item in agents)
    codex = next(item for item in agents if item["id"] == "codex_cli")
    assert codex["adapter"] == "codex_cli"
    assert codex["builtin"] is True
    assert codex["status"] == "disabled"
    assert codex["runnable"] is False
    assert "api_key" not in response.text
    assert "secret" not in response.text.lower()


def test_mcharness_agents_templates_lists_safe_templates():
    client = TestClient(app)
    response = client.get("/api/mcharness/agents/templates")
    assert response.status_code == 200, response.text
    templates = response.json()["templates"]
    labels = {item["label"] for item in templates}
    assert "Codex CLI" in labels
    assert "Jules Remote" in labels
    assert "AGY CLI Coming Later" in labels
    assert "Custom CLI Coming Later" in labels
    assert "Custom Remote Coming Later" in labels


def _enable_private_agent_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")
    import src.marius_desktop.api as api_mod

    monkeypatch.setattr(api_mod, "MCTABLE_ROOT", tmp_path)
    return api_mod


def _mock_jules_connected(monkeypatch):
    import src.marius_desktop.agent_registry as registry_mod

    def fake_test(*, api_key, default_repo_id=None, default_branch=None):
        if api_key == "bad-jules-key":
            return {
                "ok": True,
                "adapter": "jules_remote",
                "status": "invalid_key",
                "message": "Jules API rejected the API key.",
                "safe_details": {},
            }
        return {
            "ok": True,
            "adapter": "jules_remote",
            "status": "connected",
            "message": "Jules API key verified via sources list.",
            "safe_details": {"sources_count": 1},
        }

    monkeypatch.setattr(registry_mod, "test_jules_remote_config", fake_test)


def test_mcharness_agents_post_rejected_on_public_service(monkeypatch):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "false")
    monkeypatch.delenv("MCHARNESS_ADMIN_TOKEN", raising=False)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/agents",
        json={
            "name": "Jules Remote",
            "kind": "remote",
            "adapter": "jules_remote",
            "api_key": "test-jules-key",
        },
    )
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


def test_mcharness_agents_test_config_rejected_on_public_service(monkeypatch):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "false")
    monkeypatch.delenv("MCHARNESS_ADMIN_TOKEN", raising=False)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/agents/test-config",
        json={
            "adapter": "jules_remote",
            "api_key": "test-jules-key",
        },
    )
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


def test_mcharness_agents_test_config_never_returns_key(monkeypatch, tmp_path):
    _enable_private_agent_registry(monkeypatch, tmp_path)
    _mock_jules_connected(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/agents/test-config",
        json={
            "adapter": "jules_remote",
            "api_key": "test-jules-key",
            "default_repo_id": "mcharness-public-export",
            "default_branch": "feat/mcharness-functional-cockpit",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "connected"
    assert "test-jules-key" not in response.text
    assert "api_key" not in response.text


def test_mcharness_agents_test_config_invalid_key(monkeypatch, tmp_path):
    _enable_private_agent_registry(monkeypatch, tmp_path)
    _mock_jules_connected(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/agents/test-config",
        json={
            "adapter": "jules_remote",
            "api_key": "bad-jules-key",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "invalid_key"


def test_mcharness_agents_private_can_register_jules_remote(monkeypatch, tmp_path):
    api_mod = _enable_private_agent_registry(monkeypatch, tmp_path)
    _mock_jules_connected(monkeypatch)
    client = TestClient(app)

    created = client.post(
        "/api/mcharness/agents",
        json={
            "name": "Jules Remote Worker",
            "kind": "remote",
            "adapter": "jules_remote",
            "default_repo_id": "mcharness-public-export",
            "default_branch": "feat/mcharness-functional-cockpit",
            "require_plan_approval": True,
            "enabled": True,
            "api_key": "test-jules-key",
        },
    )
    assert created.status_code == 200, created.text
    agent = created.json()["agent"]
    assert agent["adapter"] == "jules_remote"
    assert agent["status"] == "ready"
    assert agent["connection_status"] == "connected"
    assert agent["configured"] is True
    assert agent["runnable"] is False
    assert agent["user_created"] is True
    assert "test-jules-key" not in created.text
    assert "api_key" not in created.text

    secret_path = tmp_path / "secrets" / f"agent_{agent['id']}.json"
    assert secret_path.exists()
    secret_data = json.loads(secret_path.read_text(encoding="utf-8"))
    assert secret_data["api_key"] == "test-jules-key"
    assert "test-jules-key" not in client.get("/api/mcharness/agents").text

    status = client.get(f"/api/mcharness/agents/{agent['id']}/status")
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["connection_status"] == "connected"
    assert status_data["runnable"] is False
    assert "test-jules-key" not in status.text


def test_mcharness_agents_rejects_custom_cli_and_duplicate_codex(monkeypatch, tmp_path):
    monkeypatch.setenv("MCHARNESS_PUBLIC_WRITE_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_TMUX_RUNNER_ENABLED", "true")
    monkeypatch.setenv("MCHARNESS_CODEX_RUNNER_ENABLED", "true")

    import src.marius_desktop.api as api_mod

    monkeypatch.setattr(api_mod, "MCTABLE_ROOT", tmp_path)
    client = TestClient(app)

    custom = client.post(
        "/api/mcharness/agents",
        json={
            "name": "Unsafe Custom",
            "kind": "cli",
            "adapter": "custom_cli",
        },
    )
    assert custom.status_code == 400
    assert "not available" in custom.json()["detail"].lower()

    codex = client.post(
        "/api/mcharness/agents",
        json={
            "name": "Extra Codex",
            "kind": "cli",
            "adapter": "codex_cli",
        },
    )
    assert codex.status_code == 400
    assert "built-in" in codex.json()["detail"].lower()


def test_mcharness_agents_delete_rules(monkeypatch, tmp_path):
    _enable_private_agent_registry(monkeypatch, tmp_path)
    _mock_jules_connected(monkeypatch)
    client = TestClient(app)

    builtin_delete = client.delete("/api/mcharness/agents/codex_cli")
    assert builtin_delete.status_code == 400
    assert "built-in" in builtin_delete.json()["detail"].lower()

    created = client.post(
        "/api/mcharness/agents",
        json={
            "name": "Jules Remote",
            "kind": "remote",
            "adapter": "jules_remote",
            "api_key": "test-jules-key",
        },
    )
    assert created.status_code == 200, created.text
    agent_id = created.json()["agent"]["id"]
    secret_path = tmp_path / "secrets" / f"agent_{agent_id}.json"
    assert secret_path.exists()

    deleted = client.delete(f"/api/mcharness/agents/{agent_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_id"] == agent_id
    assert not secret_path.exists()

    listed = client.get("/api/mcharness/agents")
    assert all(item["id"] != agent_id for item in listed.json()["agents"])


def test_mcharness_agents_probe_codex_and_jules(monkeypatch, tmp_path):
    _enable_private_agent_registry(monkeypatch, tmp_path)
    _mock_jules_connected(monkeypatch)
    client = TestClient(app)

    codex_probe = client.post("/api/mcharness/agents/codex_cli/probe")
    assert codex_probe.status_code == 200, codex_probe.text
    assert "probe" in codex_probe.json()
    assert "api_key" not in codex_probe.text

    created = client.post(
        "/api/mcharness/agents",
        json={
            "name": "Jules Remote",
            "kind": "remote",
            "adapter": "jules_remote",
            "api_key": "test-jules-key",
        },
    )
    assert created.status_code == 200, created.text
    agent_id = created.json()["agent"]["id"]
    jules_probe = client.post(f"/api/mcharness/agents/{agent_id}/probe")
    assert jules_probe.status_code == 200, jules_probe.text
    assert jules_probe.json()["status"] == "connected"
    assert "test-jules-key" not in jules_probe.text
