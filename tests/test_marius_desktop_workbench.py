import shutil

import pytest
from fastapi.testclient import TestClient

from src.marius_desktop.captain import CAPTAIN_ROOT
from src.marius_desktop.graph import CHECKPOINT_DB_PATH, TASKS_DIR
from src.marius_desktop.worker import RUNS_DIR
from src.marius_desktop.workbench import WORKBENCH_ROOT
from src.server.api import app


@pytest.fixture(autouse=True)
def clean_workbench_state():
    for directory in [WORKBENCH_ROOT, TASKS_DIR, RUNS_DIR, CHECKPOINT_DB_PATH.parent, CAPTAIN_ROOT]:
        if directory.exists():
            shutil.rmtree(directory)
    yield
    for directory in [WORKBENCH_ROOT, TASKS_DIR, RUNS_DIR, CHECKPOINT_DB_PATH.parent, CAPTAIN_ROOT]:
        if directory.exists():
            shutil.rmtree(directory)


def test_workbench_status_and_catalogs_are_local_only():
    client = TestClient(app)

    status_response = client.get("/api/marius/workbench/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["service"] == "marius-workbench"
    assert status["status"] == "online"
    assert status["local_only"] is True
    assert status["fake_worker_only"] is True
    assert status["real_agent_launch_disabled"] is True
    assert status["arbitrary_command_execution_disabled"] is True
    assert status["workbench_root"].endswith("_mctable/workbench")

    tools_response = client.get("/api/marius/workbench/tools")
    assert tools_response.status_code == 200
    tools = tools_response.json()
    assert any(tool["name"] == "fake_worker_runner" for tool in tools)
    assert any(tool["name"] == "local_mcp" for tool in tools)

    safety_response = client.get("/api/marius/workbench/safety-profiles")
    assert safety_response.status_code == 200
    safety_profiles = safety_response.json()
    assert any(profile["profile_id"] == "operator_local" for profile in safety_profiles)
    operator = next(profile for profile in safety_profiles if profile["profile_id"] == "operator_local")
    assert operator["fake_worker_only"] is True
    assert operator["real_agent_launch_disabled"] is True

    gitignore = (WORKBENCH_ROOT.parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert "_mctable/workbench/" in gitignore


def test_workbench_agent_thread_message_and_gate_flow():
    client = TestClient(app)

    agent_response = client.post(
        "/api/marius/workbench/agents",
        json={
            "agent_id": "agent_alpha",
            "name": "Agent Alpha",
            "role": "planner",
            "status": "active",
            "safety_profile_id": "operator_local",
            "allowed_threads": [],
            "notes": "Local planning only.",
        },
    )
    assert agent_response.status_code == 200
    agent = agent_response.json()
    assert agent["agent_id"] == "agent_alpha"

    thread_response = client.post(
        "/api/marius/workbench/threads",
        json={
            "thread_id": "thread_alpha",
            "agent_id": "agent_alpha",
            "title": "Plan the workbench",
            "objective": "Model agents, threads, messages, and safety locally.",
            "status": "open",
            "next_action": "inspect",
            "prompt_queue": [
                {"prompt_id": "p1", "title": "Check status", "notes": "Keep it local."},
            ],
            "minion_tasks": [],
            "evidence_records": [],
            "hard_gates": [],
            "planned_acceptance_commands": [],
            "recovery_hint": None,
            "notes": "No workflow truth here.",
        },
    )
    assert thread_response.status_code == 200
    thread = thread_response.json()
    assert thread["thread_id"] == "thread_alpha"
    assert thread["message_count"] == 0
    assert thread["proof_gate_count"] == 0

    message_response = client.post(
        "/api/marius/workbench/threads/thread_alpha/messages",
        json={"author": "operator", "kind": "planning", "content": "Keep the workbench local-only."},
    )
    assert message_response.status_code == 200
    message = message_response.json()
    assert message["thread_id"] == "thread_alpha"
    assert message["status"] == "recorded"

    thread_detail = client.get("/api/marius/workbench/threads/thread_alpha")
    assert thread_detail.status_code == 200
    thread_data = thread_detail.json()
    assert thread_data["message_count"] == 1
    assert thread_data["messages"][0]["content"] == "Keep the workbench local-only."
    assert thread_data["prompt_queue"][0]["prompt_id"] == "p1"

    gate_response = client.post(
        "/api/marius/workbench/threads/thread_alpha/proof-gates",
        json={"kind": "manual_review", "reason": "Proof needed", "triggered_by": "operator"},
    )
    assert gate_response.status_code == 200
    gated = gate_response.json()
    assert gated["status"] == "blocked"
    assert gated["proof_gate_count"] == 1
    gate_id = gated["hard_gates"][0]["gate_id"]

    decision_response = client.post(
        f"/api/marius/workbench/threads/thread_alpha/proof-gates/{gate_id}/decision",
        json={"decision": "approve", "actor": "operator", "reviewer_note": "Approved locally."},
    )
    assert decision_response.status_code == 200
    decided = decision_response.json()
    assert decided["status"] == "open"
    assert decided["hard_gates"][0]["decision"] == "approve"


def test_workbench_friendly_thread_and_message_contracts():
    client = TestClient(app)

    client.post(
        "/api/marius/workbench/agents",
        json={
            "agent_id": "agent_gamma",
            "name": "Agent Gamma",
            "role": "planner",
            "status": "active",
            "safety_profile_id": "operator_local",
            "allowed_threads": [],
            "notes": None,
        },
    )

    friendly_thread = client.post(
        "/api/marius/workbench/threads",
        json={"title": "Friendly thread", "goal": "Use the cockpit friendly contract."},
    )
    assert friendly_thread.status_code == 200
    thread = friendly_thread.json()
    assert thread["thread_id"]
    assert thread["title"] == "Friendly thread"
    assert thread["objective"] == "Use the cockpit friendly contract."

    raw_thread = client.post(
        "/api/marius/workbench/threads",
        json={
            "thread_id": "thread_raw",
            "title": "Raw thread",
            "objective": "Keep the internal contract available.",
        },
    )
    assert raw_thread.status_code == 200
    assert raw_thread.json()["thread_id"] == "thread_raw"

    raw_message = client.post(
        f"/api/marius/workbench/threads/{thread['thread_id']}/messages",
        json={"author": "operator", "kind": "planning", "content": "Use the friendly cockpit form."},
    )
    assert raw_message.status_code == 200
    assert raw_message.json()["author"] == "operator"
    assert raw_message.json()["kind"] == "planning"

    friendly_message = client.post(
        f"/api/marius/workbench/threads/{thread['thread_id']}/messages",
        json={"role": "operator", "kind": "instruction", "content": "Plan the next step."},
    )
    assert friendly_message.status_code == 200
    friendly_payload = friendly_message.json()
    assert friendly_payload["author"] == "operator"
    assert friendly_payload["kind"] == "planning"

    blocked_raw = client.post(
        f"/api/marius/workbench/threads/{thread['thread_id']}/messages",
        json={"author": "operator", "kind": "command_request", "content": "run rm -rf /"},
    )
    assert blocked_raw.status_code == 400
    blocked_raw_payload = blocked_raw.json()
    assert blocked_raw_payload["status"] == "blocked"
    assert "blocked" in blocked_raw_payload["reason"].lower()
    assert blocked_raw_payload["recovery_hint"]

    blocked_friendly = client.post(
        f"/api/marius/workbench/threads/{thread['thread_id']}/messages",
        json={"role": "operator", "kind": "command_request", "content": "run rm -rf /"},
    )
    assert blocked_friendly.status_code == 400
    blocked_friendly_payload = blocked_friendly.json()
    assert blocked_friendly_payload["status"] == "blocked"
    assert "blocked" in blocked_friendly_payload["reason"].lower()
    assert blocked_friendly_payload["recovery_hint"]

    thread_detail = client.get(f"/api/marius/workbench/threads/{thread['thread_id']}")
    assert thread_detail.status_code == 200
    detail = thread_detail.json()
    assert len(detail["messages"]) == 2
    assert any(message["kind"] == "planning" for message in detail["messages"])


def test_workbench_rejects_command_request_messages_and_persists_registry_records():
    client = TestClient(app)

    client.post(
        "/api/marius/workbench/agents",
        json={
            "agent_id": "agent_beta",
            "name": "Agent Beta",
            "role": "scribe",
            "status": "active",
            "safety_profile_id": "operator_local",
            "allowed_threads": [],
            "notes": None,
        },
    )
    client.post(
        "/api/marius/workbench/threads",
        json={
            "thread_id": "thread_beta",
            "agent_id": "agent_beta",
            "title": "Persist registry items",
            "objective": "Save skills, memories, and artifacts locally.",
            "status": "open",
            "next_action": "inspect",
            "prompt_queue": [],
            "minion_tasks": [],
            "evidence_records": [],
            "hard_gates": [],
            "planned_acceptance_commands": [],
            "recovery_hint": None,
            "notes": None,
        },
    )

    rejected = client.post(
        "/api/marius/workbench/threads/thread_beta/messages",
        json={
            "author": "operator",
            "kind": "command_request",
            "content": "run rm -rf /",
        },
    )
    assert rejected.status_code == 400
    payload = rejected.json()
    assert payload["status"] == "blocked"
    assert "blocked" in payload["reason"].lower()
    assert payload["recovery_hint"]

    skill_response = client.post(
        "/api/marius/workbench/skills",
        json={
            "skill_id": "status_auditor",
            "title": "Status Auditor",
            "description": "Reviews backend and cockpit truth.",
            "path": "docs/architecture.md",
            "enabled": True,
            "notes": "Local planning only.",
        },
    )
    assert skill_response.status_code == 200
    assert client.get("/api/marius/workbench/skills").json()[0]["skill_id"] == "status_auditor"

    memory_response = client.post(
        "/api/marius/workbench/memories",
        json={
            "memory_id": "release_notes",
            "scope": "workbench",
            "summary": "Keep the workbench local-only and factual.",
            "source": "operator",
            "compacted": False,
            "notes": None,
        },
    )
    assert memory_response.status_code == 200
    assert client.get("/api/marius/workbench/memories").json()[0]["memory_id"] == "release_notes"

    artifact_response = client.post(
        "/api/marius/workbench/artifacts",
        json={
            "artifact_id": "proof_pack",
            "kind": "report",
            "title": "Proof Pack",
            "path": "docs/release_candidate_report.md",
            "thread_id": "thread_beta",
            "summary": "Local proof pack.",
            "notes": None,
        },
    )
    assert artifact_response.status_code == 200
    artifacts = client.get("/api/marius/workbench/artifacts").json()
    assert artifacts[0]["artifact_id"] == "proof_pack"
