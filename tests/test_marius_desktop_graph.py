import shutil

import pytest

from src.marius_desktop.graph import (
    CHECKPOINT_DB_PATH,
    LANGGRAPH_AVAILABLE,
    MCTABLE_ROOT,
    TASKS_DIR,
    McTableTaskGraph,
)
from src.marius_desktop.worker import RUNS_DIR


@pytest.fixture(autouse=True)
def clean_mctable():
    for d in [TASKS_DIR, RUNS_DIR, MCTABLE_ROOT / "checkpoints"]:
        if d.exists():
            shutil.rmtree(d)
    yield
    for d in [TASKS_DIR, RUNS_DIR, MCTABLE_ROOT / "checkpoints"]:
        if d.exists():
            shutil.rmtree(d)


def test_graph_reports_langgraph_and_checkpoint_path():
    assert LANGGRAPH_AVAILABLE is True
    assert CHECKPOINT_DB_PATH.name == "marius_desktop.sqlite"
    assert CHECKPOINT_DB_PATH.parent.name == "checkpoints"


def test_graph_checkpoint_success_round_trip():
    graph = McTableTaskGraph()
    state = graph.create_task(
        "task-succeed",
        "Test Success Task",
        "Success description",
        "fake-worker-success",
        [],
    )
    state = graph.drive_task_to_review(state.task_id)

    assert state.task_id == "task-succeed"
    assert state.status == "paused"
    assert state.current_step == "human_review_gate"
    assert state.worker_run_id is not None
    assert state.worker_result is not None
    assert state.worker_result.status == "success"
    assert CHECKPOINT_DB_PATH.exists()

    fresh_graph = McTableTaskGraph()
    reloaded = fresh_graph.load_state(state.task_id)
    assert reloaded.status == "paused"
    assert reloaded.current_step == "human_review_gate"
    assert reloaded.worker_run_id == state.worker_run_id

    resumed = fresh_graph.resume_task(
        task_id=state.task_id,
        decision="approve",
        actor="operator",
        reviewer_note="Looks good.",
        state_patch={},
    )
    assert resumed.status == "completed"
    assert resumed.proof_status == "approved"
    assert resumed.current_step == "complete"

    persisted = McTableTaskGraph().load_state(state.task_id)
    assert persisted.status == "completed"
    assert persisted.proof_status == "approved"


def test_graph_checkpoint_failure_and_reject_round_trip():
    graph = McTableTaskGraph()
    state = graph.create_task(
        "task-fail",
        "Test Fail Task",
        "Fail description",
        "fake-worker-fail",
        [],
    )
    state = graph.drive_task_to_review(state.task_id)

    assert state.status == "paused"
    assert state.current_step == "human_review_gate"
    assert state.worker_result is not None
    assert state.worker_result.status == "failed"
    assert state.recovery_hint is not None
    assert "fake-worker-success" in state.recovery_hint

    resumed = graph.resume_task(
        task_id=state.task_id,
        decision="reject",
        actor="operator",
        reviewer_note="Failed worker execution confirmed.",
        state_patch={},
    )
    assert resumed.status == "failed"
    assert resumed.proof_status == "rejected"
    assert resumed.current_step == "complete"


def test_graph_edit_state_accepts_patch_and_keeps_pause():
    graph = McTableTaskGraph()
    state = graph.create_task(
        "task-edit",
        "Test Edit Task",
        "Edit description",
        "fake-worker-success",
        [],
    )
    state = graph.drive_task_to_review(state.task_id)

    edited = graph.resume_task(
        task_id=state.task_id,
        decision="edit_state",
        actor="operator",
        reviewer_note=None,
        state_patch={"recovery_hint": "patched through graph"},
    )
    assert edited.status == "paused"
    assert edited.current_step == "human_review_gate"
    assert edited.recovery_hint == "patched through graph"

    reloaded = McTableTaskGraph().load_state(state.task_id)
    assert reloaded.recovery_hint == "patched through graph"
