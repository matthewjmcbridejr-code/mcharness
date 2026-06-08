import shutil
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.marius_desktop.captain import CAPTAIN_ROOT
from src.marius_desktop.workbench import WORKBENCH_ROOT
from src.server.api import app


@pytest.fixture(autouse=True)
def clean_captain_store():
    for directory in [CAPTAIN_ROOT, WORKBENCH_ROOT]:
        if directory.exists():
            shutil.rmtree(directory)
    yield
    for directory in [CAPTAIN_ROOT, WORKBENCH_ROOT]:
        if directory.exists():
            shutil.rmtree(directory)


def test_captain_run_serializes():
    from src.marius_desktop.contracts import CaptainRun, EvidenceRecord, HardGate, MinionTask, PromptQueueItem, ScopedCommitPlan

    run = CaptainRun(
        run_id="run_test",
        objective="Verify Captain Mode",
        next_action="inspect",
        prompt_queue=[PromptQueueItem(prompt_id="p1", title="Read prompt")],
        minion_tasks=[MinionTask(minion_id="m1", scope="docs")],
        evidence_records=[
            EvidenceRecord(
                evidence_id="ev1",
                summary="proof",
                details="details",
                captured_by="captain",
                artifacts=["README.md"],
                captured_at="2026-06-07T00:00:00Z",
            )
        ],
        hard_gates=[
            HardGate(
                gate_id="g1",
                kind="security",
                reason="blocked",
                triggered_by="review",
                created_at="2026-06-07T00:00:00Z",
            )
        ],
        scoped_commit_plan=ScopedCommitPlan(commit_message="test", files=["README.md"]),
        planned_acceptance_commands=["python -m pytest -q tests/test_marius_desktop_captain.py"],
        created_at="2026-06-07T00:00:00Z",
        updated_at="2026-06-07T00:00:00Z",
    )

    encoded = run.model_dump_json()
    decoded = CaptainRun.model_validate_json(encoded)
    assert decoded.run_id == "run_test"
    assert decoded.prompt_queue[0].title == "Read prompt"
    assert decoded.hard_gates[0].kind == "security"


def test_captain_run_can_be_created():
    client = TestClient(app)
    response = client.post(
        "/api/marius/captain/runs",
        json={
            "objective": "Prepare release queue",
            "next_action": "inspect",
            "planned_acceptance_commands": ["python -m pytest -q tests/test_marius_desktop_captain.py"],
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["objective"] == "Prepare release queue"
    assert run["status"] == "active"
    assert run["planned_acceptance_commands"] == ["python -m pytest -q tests/test_marius_desktop_captain.py"]

    list_response = client.get("/api/marius/captain/runs")
    assert list_response.status_code == 200
    assert any(item["run_id"] == run["run_id"] for item in list_response.json())


def test_captain_templates_list_get_and_run_from_template():
    client = TestClient(app)

    list_response = client.get("/api/marius/captain/templates")
    assert list_response.status_code == 200
    templates = list_response.json()
    template_ids = {item["template_id"] for item in templates}
    assert {"release_qa", "ui_polish", "docs_audit", "test_triage", "marathon_queue"} <= template_ids

    template_response = client.get("/api/marius/captain/templates/release_qa")
    assert template_response.status_code == 200
    template = template_response.json()
    assert template["prompt_queue"]
    assert template["hard_gates"]

    run_response = client.post(
        "/api/marius/captain/runs/from-template",
        json={"template": template, "next_action": "inspect"},
    )
    assert run_response.status_code == 200
    run = run_response.json()
    assert run["objective"] == template["objective"]
    assert run["prompt_queue"] == template["prompt_queue"]
    assert run["hard_gates"] == template["hard_gates"]
    assert run["planned_acceptance_commands"] == template["planned_acceptance_commands"]


def test_captain_template_rejects_forbidden_content():
    client = TestClient(app)
    response = client.post(
        "/api/marius/captain/runs/from-template",
        json={
            "template": {
                "template_id": "unsafe",
                "title": "Unsafe",
                "objective": "Try to launch a public worker",
                "prompt_queue": [],
                "minion_tasks": [],
                "hard_gates": [],
                "planned_acceptance_commands": ["rm -rf /"],
            },
            "next_action": "inspect",
        },
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_evidence_can_be_added():
    client = TestClient(app)
    created = client.post("/api/marius/captain/runs", json={"objective": "Evidence flow", "next_action": "inspect"})
    run_id = created.json()["run_id"]

    response = client.post(
        f"/api/marius/captain/runs/{run_id}/evidence",
        json={
            "summary": "Backend verification passed",
            "details": "Captain Mode should only store text evidence.",
            "captured_by": "captain",
            "artifacts": ["scripts/verify_marius_desktop_backend.py"],
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert len(run["evidence_records"]) == 1
    assert run["evidence_records"][0]["summary"] == "Backend verification passed"


def test_manual_evidence_and_gate_decision_are_recorded():
    client = TestClient(app)
    created = client.post("/api/marius/captain/runs", json={"objective": "Manual evidence flow", "next_action": "inspect"})
    run_id = created.json()["run_id"]

    evidence_response = client.post(
        f"/api/marius/captain/runs/{run_id}/evidence",
        json={
            "kind": "manual_observation",
            "summary": "Observed the cockpit workflow",
            "status": "recorded",
            "command_text": "python -m pytest -q tests/test_marius_desktop_captain.py",
            "details": "Captured from the local demo run.",
            "captured_by": "operator",
            "artifacts": [],
        },
    )
    assert evidence_response.status_code == 200
    run = evidence_response.json()
    evidence = run["evidence_records"][0]
    assert evidence["kind"] == "manual_observation"
    assert evidence["status"] == "recorded"
    assert evidence["command_text"] == "python -m pytest -q tests/test_marius_desktop_captain.py"

    gate_response = client.post(
        f"/api/marius/captain/runs/{run_id}/gate",
        json={"kind": "manual_review", "reason": "Needs operator review", "triggered_by": "operator"},
    )
    assert gate_response.status_code == 200
    run = gate_response.json()
    gate_id = run["hard_gates"][0]["gate_id"]

    decision_response = client.post(
        f"/api/marius/captain/runs/{run_id}/gates/{gate_id}/decision",
        json={"decision": "approve", "actor": "operator", "reviewer_note": "Recorded for audit only"},
    )
    assert decision_response.status_code == 200
    decided_run = decision_response.json()
    decided_gate = decided_run["hard_gates"][0]
    assert decided_gate["decision"] == "approve"
    assert decided_gate["decision_actor"] == "operator"
    assert decided_gate["decision_note"] == "Recorded for audit only"


def test_hard_gate_blocks_continuation():
    client = TestClient(app)
    created = client.post("/api/marius/captain/runs", json={"objective": "Gate flow", "next_action": "inspect"})
    run_id = created.json()["run_id"]

    gate_response = client.post(
        f"/api/marius/captain/runs/{run_id}/gate",
        json={"kind": "security", "reason": "unsafe claim detected", "triggered_by": "auditor"},
    )
    assert gate_response.status_code == 200
    run = gate_response.json()
    assert run["status"] == "blocked"
    assert len(run["hard_gates"]) == 1


def test_next_action_refuses_when_gated():
    client = TestClient(app)
    created = client.post("/api/marius/captain/runs", json={"objective": "Gate flow", "next_action": "inspect"})
    run_id = created.json()["run_id"]
    client.post(
        f"/api/marius/captain/runs/{run_id}/gate",
        json={"kind": "policy", "reason": "prompt blocked", "triggered_by": "auditor"},
    )

    response = client.post(
        f"/api/marius/captain/runs/{run_id}/next",
        json={"next_action": "continue", "planned_acceptance_commands": ["python -m pytest -q tests/test_marius_desktop_captain.py"]},
    )
    assert response.status_code == 409
    assert "blocked" in response.json()["detail"].lower()


def test_command_execution_requests_are_blocked():
    client = TestClient(app)
    created = client.post("/api/marius/captain/runs", json={"objective": "Execution guard", "next_action": "inspect"})
    run_id = created.json()["run_id"]

    response = client.post(
        f"/api/marius/captain/runs/{run_id}/next",
        json={
            "next_action": "continue",
            "planned_acceptance_commands": ["rm -rf /"],
            "command_execution_request": True,
        },
    )
    assert response.status_code == 501
    assert "not_implemented" in response.json()["detail"]


def test_captain_state_machine_models_serialize_and_persist():
    from src.marius_desktop.captain import CaptainPlan, CaptainState, CaptainTransition, MinionAssignment, PromptQueueItem

    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    state = CaptainState(
        captain_run_id="captain_abc123",
        thread_id="thread_abc123",
        run_id="captain_abc123",
        status="planning",
        objective="Polish the cockpit UI",
        current_step="plan",
        created_at=now,
        updated_at=now,
    )
    plan = CaptainPlan(
        plan_id="plan_abc123",
        captain_run_id=state.captain_run_id,
        summary="Deterministic plan",
        assumptions=["Local only"],
        steps=["Step one", "Step two"],
        acceptance_criteria=["Prove persistence"],
        risks=["Human gate"],
        requires_human_gate=True,
        created_at=now,
    )
    queue_item = PromptQueueItem(
        queue_item_id="queue_abc123",
        captain_run_id=state.captain_run_id,
        title="Queue item",
        prompt="Review the plan",
        priority=1,
        target_role="reviewer",
        allowed_files=["README.md"],
        forbidden_actions=["shell"],
        acceptance_checks=["Persist the record"],
        created_at=now,
        updated_at=now,
    )
    assignment = MinionAssignment(
        assignment_id="assign_abc123",
        captain_run_id=state.captain_run_id,
        queue_item_id=queue_item.queue_item_id,
        role="reviewer",
        title="Queue item",
        instructions="Review the plan",
        evidence_required=["Persist the record"],
        created_at=now,
        updated_at=now,
    )
    transition = CaptainTransition(
        transition_id="transition_abc123",
        captain_run_id=state.captain_run_id,
        from_status="intake",
        to_status="planning",
        reason="Created the initial plan",
        created_at=now,
    )

    state.plan = plan
    state.prompt_queue = [queue_item]
    state.assignments = [assignment]
    state.transitions = [transition]

    encoded = state.model_dump_json()
    decoded = CaptainState.model_validate_json(encoded)
    assert decoded.captain_run_id == "captain_abc123"
    assert decoded.plan.summary == "Deterministic plan"
    assert decoded.prompt_queue[0].prompt == "Review the plan"
    assert decoded.assignments[0].queue_item_id == queue_item.queue_item_id
    assert decoded.transitions[0].to_status == "planning"


def test_captain_state_machine_flow_records_transitions_queue_and_gates():
    client = TestClient(app)

    thread_response = client.post(
        "/api/marius/workbench/threads",
        json={
            "thread_id": "thread_captain_state",
            "title": "Captain state thread",
            "objective": "Model the public Captain Mode state machine.",
        },
    )
    assert thread_response.status_code == 200

    create_response = client.post(
        "/api/marius/workbench/threads/thread_captain_state/captain-runs",
        json={"objective": "Polish the cockpit UI for public demo"},
    )
    assert create_response.status_code == 200
    state = create_response.json()
    assert state["captain_run_id"] == state["run_id"]
    assert state["status"] == "intake"

    state_response = client.get(f"/api/marius/captain/runs/{state['captain_run_id']}")
    assert state_response.status_code == 200
    assert state_response.json()["objective"] == "Polish the cockpit UI for public demo"

    plan_response = client.post(
        f"/api/marius/captain/runs/{state['captain_run_id']}/plan",
        json={"instruction": "Create a bounded plan with tests and proof gates."},
    )
    assert plan_response.status_code == 200
    planned = plan_response.json()
    assert planned["status"] == "planning"
    assert planned["plan"]["requires_human_gate"] is True

    queue_response = client.post(f"/api/marius/captain/runs/{state['captain_run_id']}/queue")
    assert queue_response.status_code == 200
    queued = queue_response.json()
    assert queued["status"] == "blocked_on_gate"
    assert len(queued["prompt_queue"]) >= 1
    assert queued["proof_gate_id"]

    assignments_response = client.post(f"/api/marius/captain/runs/{state['captain_run_id']}/assign-minions")
    assert assignments_response.status_code == 200
    assigned = assignments_response.json()
    assert len(assigned["assignments"]) == len(assigned["prompt_queue"])
    assert assigned["status"] in {"blocked_on_gate", "waiting_for_evidence"}

    queue_list = client.get(f"/api/marius/captain/runs/{state['captain_run_id']}/queue")
    assert queue_list.status_code == 200
    assert len(queue_list.json()) == len(assigned["prompt_queue"])

    assignments_list = client.get(f"/api/marius/captain/runs/{state['captain_run_id']}/assignments")
    assert assignments_list.status_code == 200
    assert len(assignments_list.json()) == len(assigned["assignments"])

    transitions_response = client.get(f"/api/marius/captain/runs/{state['captain_run_id']}/transitions")
    assert transitions_response.status_code == 200
    assert len(transitions_response.json()) >= 4

    workbench_run = client.get(f"/api/marius/workbench/runs/{state['run_id']}")
    assert workbench_run.status_code == 200
    assert workbench_run.json()["proof_gates"]

    blocked_continue = client.post(f"/api/marius/captain/runs/{state['captain_run_id']}/continue")
    assert blocked_continue.status_code == 200
    blocked_payload = blocked_continue.json()
    assert blocked_payload["status"] == "blocked"
    assert "Approve/reject" in blocked_payload["recovery_hint"]

    gate_id = blocked_payload["state"]["proof_gate_id"]
    approved_gate = client.post(
        f"/api/marius/workbench/proof-gates/{gate_id}/decision",
        json={"actor": "operator", "decision": "approved", "note": "Approved locally."},
    )
    assert approved_gate.status_code == 200

    ready_continue = client.post(f"/api/marius/captain/runs/{state['captain_run_id']}/continue")
    assert ready_continue.status_code == 200
    ready_payload = ready_continue.json()
    assert ready_payload["status"] in {"safe_noop", "ready_to_continue"}
    assert ready_payload["state"]["status"] in {"ready_to_continue", "queued"}


def test_captain_state_machine_descriptor_is_local_only():
    client = TestClient(app)
    response = client.get("/api/marius/captain/state-machine")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "mcharness.captain.v0.2"
    assert payload["local_only"] is True
    assert payload["fake_worker_only"] is True
    assert payload["real_external_agent_launch_disabled"] is True
    assert payload["public_worker_launch_disabled"] is True
    assert payload["arbitrary_shell_execution_disabled"] is True
