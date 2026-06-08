import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from src.marius_desktop.contracts import (
    CaptainTemplate,
    HardGate,
    MemoryContext,
    MinionTask,
    PromptQueueItem,
    WorkerResult,
    HumanDecision,
    TaskState,
    WorkerRun,
    ProofReview,
    ToolResult,
    CapabilityStatus
)

def test_models_importable():
    # Verify that all contracts are importable
    assert MemoryContext is not None
    assert WorkerResult is not None
    assert HumanDecision is not None
    assert TaskState is not None
    assert WorkerRun is not None
    assert ProofReview is not None
    assert ToolResult is not None
    assert CapabilityStatus is not None

def test_task_state_serialization():
    now = datetime.now(timezone.utc)
    state = TaskState(
        task_id="test-task-1",
        title="Test Task",
        description="Pydantic validation test",
        status="queued",
        risk_level="low",
        proof_status="not_required",
        current_step="create_task",
        agent_id="fake-agent",
        command="fake-worker-success",
        args=[],
        metadata={},
        memory_context=None,
        worker_run_id=None,
        worker_result=None,
        human_decision=None,
        recovery_hint=None,
        created_at=now,
        updated_at=now
    )
    
    serialized = state.model_dump_json()
    deserialized = TaskState.model_validate_json(serialized)
    assert deserialized.task_id == "test-task-1"
    assert deserialized.status == "queued"
    assert deserialized.created_at == now

def test_invalid_decision_rejected():
    # Invalid values should raise ValidationError
    with pytest.raises(ValidationError):
        HumanDecision(
            decision="invalid_decision_value",  # Should be approve/reject/edit_state
            actor="operator",
            reviewer_note="Note",
            state_patch={},
            decided_at=datetime.now(timezone.utc)
        )

def test_worker_result_validation():
    # WorkerResult status validation
    with pytest.raises(ValidationError):
        WorkerResult(
            run_id="run-1",
            task_id="task-1",
            status="invalid_status",  # Should be success/failed/cancelled/blocked
            summary="summary"
        )


def test_captain_template_serialization():
    now = datetime.now(timezone.utc)
    template = CaptainTemplate(
        template_id="release_qa",
        title="Release QA",
        objective="Verify the release candidate.",
        prompt_queue=[PromptQueueItem(prompt_id="p1", title="Review status")],
        minion_tasks=[MinionTask(minion_id="m1", role="auditor", scope="Review the local API")],
        hard_gates=[
            HardGate(
                gate_id="g1",
                kind="scope",
                reason="Keep the work local.",
                triggered_by="captain",
                created_at=now,
            )
        ],
        planned_acceptance_commands=["python -m pytest -q tests/test_marius_desktop_captain.py"],
    )

    serialized = template.model_dump_json()
    deserialized = CaptainTemplate.model_validate_json(serialized)
    assert deserialized.template_id == "release_qa"
    assert deserialized.minion_tasks[0].role == "auditor"
    assert deserialized.hard_gates[0].gate_id == "g1"
