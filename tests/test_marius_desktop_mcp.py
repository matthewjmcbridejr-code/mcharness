import asyncio
import shutil
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.marius_desktop.graph import CHECKPOINT_DB_PATH, TASKS_DIR
from src.marius_desktop.mcp import LOCAL_MCP_REGISTRY, create_mcp_server
from src.marius_desktop.worker import RUNS_DIR, WorkerStub
from src.server.api import app


@pytest.fixture(autouse=True)
def clean_marius_desktop_state():
    for d in [TASKS_DIR, RUNS_DIR, CHECKPOINT_DB_PATH.parent]:
        if d.exists():
            shutil.rmtree(d)
    yield
    for d in [TASKS_DIR, RUNS_DIR, CHECKPOINT_DB_PATH.parent]:
        if d.exists():
            shutil.rmtree(d)


def _tool_json(server, tool_name: str, **kwargs):
    async def _invoke():
        result = await server.call_tool(tool_name, kwargs)
        if isinstance(result, tuple) and len(result) > 1 and isinstance(result[1], dict):
            return result[1]
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result[0]
        raise AssertionError(f"Unexpected MCP tool response shape: {type(result)!r} {result!r}")

    return asyncio.run(_invoke())


def test_capabilities_are_safe_and_local_only():
    server = create_mcp_server()
    assert server is not None

    payload = _tool_json(server, "mctable_capabilities")
    data = payload["data"]

    assert payload["schema"] == "marius_desktop.mcp.v1"
    assert payload["tool"] == "mctable_capabilities"
    assert data["local_only"] is True
    assert data["transport"] == "stdio"
    assert data["server_available"] is True
    assert data["checkpoint_exists"] in {True, False}
    assert "mctable_task_create" in data["tools"]
    langgraph = next(item for item in data["capabilities"] if item["name"] == "langgraph")
    assert langgraph["status"] == "available"
    worker = next(item for item in data["capabilities"] if item["name"] == "worker_runner")
    assert worker["status"] == "available"


def test_task_create_get_and_resume_via_mcp():
    server = create_mcp_server()
    assert server is not None

    created = _tool_json(
        server,
        "mctable_task_create",
        task_id="mcp_task_01",
        title="MCP task",
        description="Create a task through MCP",
        command="fake-worker-success",
        args=[],
    )
    task = created["data"]
    assert task["task_id"] == "mcp_task_01"
    assert task["command"] == "fake-worker-success"
    assert task["status"] == "paused"
    assert task["current_step"] == "human_review_gate"
    assert task["proof_status"] == "needs_review"
    assert CHECKPOINT_DB_PATH.exists()

    fetched = _tool_json(server, "mctable_task_get", task_id="mcp_task_01")
    assert fetched["data"]["status"] == "paused"
    assert fetched["data"]["current_step"] == "human_review_gate"

    resumed = _tool_json(
        server,
        "mctable_task_resume",
        task_id="mcp_task_01",
        decision="approve",
        actor="operator",
        reviewer_note="Approved through MCP",
        state_patch={},
    )
    assert resumed["data"]["status"] == "completed"
    assert resumed["data"]["proof_status"] == "approved"


def test_task_resume_reject_and_edit_state_validation():
    server = create_mcp_server()
    assert server is not None

    reject_created = _tool_json(
        server,
        "mctable_task_create",
        task_id="mcp_task_02",
        title="Reject task",
        description="Reject path",
        command="fake-worker-success",
        args=[],
    )
    assert reject_created["data"]["task_id"] == "mcp_task_02"

    rejected = _tool_json(
        server,
        "mctable_task_resume",
        task_id="mcp_task_02",
        decision="reject",
        actor="operator",
        reviewer_note="Not acceptable",
        state_patch={},
    )
    assert rejected["data"]["status"] == "failed"
    assert rejected["data"]["proof_status"] == "rejected"

    edit_created = _tool_json(
        server,
        "mctable_task_create",
        task_id="mcp_task_03",
        title="Edit task",
        description="Edit path",
        command="fake-worker-success",
        args=[],
    )
    assert edit_created["data"]["task_id"] == "mcp_task_03"

    edited = _tool_json(
        server,
        "mctable_task_resume",
        task_id="mcp_task_03",
        decision="edit_state",
        actor="operator",
        reviewer_note=None,
        state_patch={"recovery_hint": "patched through MCP"},
    )
    assert edited["data"]["status"] == "paused"
    assert edited["data"]["recovery_hint"] == "patched through MCP"

    with pytest.raises(ValidationError):
        LOCAL_MCP_REGISTRY.mctable_task_resume(
            task_id="mcp_task_03",
            decision="invalid",
            actor="operator",
            reviewer_note=None,
            state_patch={},
        )


def test_worker_status_and_logs_are_persisted():
    server = create_mcp_server()
    assert server is not None

    run_id = WorkerStub.start_run("agent-1", "task-worker-01", "fake-worker-success", [])
    time.sleep(0.5)

    status = _tool_json(server, "mctable_worker_status", run_id=run_id)
    logs = _tool_json(server, "mctable_worker_logs", run_id=run_id)

    assert status["data"]["run_id"] == run_id
    assert status["data"]["status"] == "success"
    assert status["data"]["exit_code"] == 0
    assert "Starting fake success worker" in logs["data"]["logs"]
    assert "Success output" in logs["data"]["logs"]


def test_mcp_rejects_unknown_commands_and_real_agents():
    server = create_mcp_server()
    assert server is not None

    with pytest.raises(Exception):
        _tool_json(
            server,
            "mctable_task_create",
            task_id="mcp_bad_01",
            title="Bad task",
            description="Unknown command should fail",
            command="rm -rf /",
            args=[],
        )

    with pytest.raises(Exception):
        _tool_json(
            server,
            "mctable_task_create",
            task_id="mcp_bad_02",
            title="Bad task",
            description="Real agent commands are blocked",
            command="grok-build-stub",
            args=[],
        )


def test_legacy_launch_routes_stay_disabled():
    client = TestClient(app)

    response = client.post(
        "/api/mctable/local/dispatch-launch",
        json={
            "title": "Legacy launch",
            "body": "Create and launch a worker.",
            "agent": "antigravity-cli",
            "repo": ".",
        },
    )
    assert response.status_code == 400
    assert "deprecated/disabled" in response.json()["detail"]

    response = client.post("/tasks/example/launch", json={})
    assert response.status_code == 404
