import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from src.marius_desktop.api import get_capabilities, get_status
from src.marius_desktop.graph import CHECKPOINT_DB_PATH, McTableTaskGraph, TASKS_DIR, checkpoint_file_exists
from src.marius_desktop.worker import WorkerStub

import langgraph


def _langgraph_version() -> str:
    try:
        return getattr(langgraph, "__version__", None) or version("langgraph")
    except PackageNotFoundError:
        return "unknown"


def _print_capabilities() -> None:
    caps = get_capabilities()
    print("\nCapabilities:")
    for cap in caps:
        print(f"- {cap.name}: {cap.status} | {cap.summary}")


def _assert_state(state, expected_status: str, expected_step: str) -> None:
    if state.status != expected_status or state.current_step != expected_step:
        print(
            f"Error: expected status={expected_status} step={expected_step}, got "
            f"status={state.status} step={state.current_step}",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    print("=== McHarness Backend Verification ===")
    print(f"LangGraph version: {_langgraph_version()}")
    print(f"Checkpoint path: {CHECKPOINT_DB_PATH}")
    print(f"Checkpoint exists initially: {checkpoint_file_exists()}")

    status = get_status()
    print("\nService status:")
    for key, value in status.items():
        print(f"- {key}: {value}")

    _print_capabilities()

    task_succeed_id = "verify-task-succeed"
    task_fail_id = "verify-task-fail"
    for tid in [task_succeed_id, task_fail_id]:
        p = TASKS_DIR / f"{tid}.json"
        if p.exists():
            p.unlink()

    graph = McTableTaskGraph()

    print(f"\nCreating task '{task_succeed_id}' with command 'fake-worker-success'...")
    state = graph.create_task(
        task_id=task_succeed_id,
        title="Verification Success Task",
        description="Verify success path",
        command="fake-worker-success",
        args=[],
    )
    state = graph.drive_task_to_review(task_succeed_id)
    _assert_state(state, "paused", "human_review_gate")
    print(f"Paused at {state.current_step} with status={state.status}")
    print(f"Checkpoint exists now: {checkpoint_file_exists()}")

    if state.worker_run_id:
        run = WorkerStub.get_status(state.worker_run_id)
        print(f"Worker run status: {run.status}, exit_code={run.exit_code}")
        logs = "".join(list(WorkerStub.stream_logs(state.worker_run_id)))
        print(f"Worker logs snippet:\n{logs.strip()}")
        res_file = Path(run.logs_path) / "result.json"
        print(f"Result file exists: {res_file.exists()}")
    else:
        print("Error: worker_run_id missing on success path.", file=sys.stderr)
        sys.exit(1)

    print("\nSubmitting human approval decision...")
    state = graph.resume_task(
        task_id=task_succeed_id,
        decision="approve",
        actor="operator",
        reviewer_note="Looks perfect.",
        state_patch={},
    )
    _assert_state(state, "completed", "complete")
    if state.proof_status != "approved":
        print("Error: success path did not approve proof.", file=sys.stderr)
        sys.exit(1)
    print("Success path verified successfully!")

    print(f"\nCreating task '{task_fail_id}' with command 'fake-worker-fail'...")
    state_fail = graph.create_task(
        task_id=task_fail_id,
        title="Verification Fail Task",
        description="Verify failure path",
        command="fake-worker-fail",
        args=[],
    )
    state_fail = graph.drive_task_to_review(task_fail_id)
    _assert_state(state_fail, "paused", "human_review_gate")

    if state_fail.worker_run_id:
        run = WorkerStub.get_status(state_fail.worker_run_id)
        print(f"Worker run status: {run.status}, exit_code={run.exit_code}")
        if state_fail.worker_result and state_fail.worker_result.recovery_hint:
            print(f"Recovery Hint (Deliberate fail): {state_fail.worker_result.recovery_hint}")
        else:
            print("Error: Failure recovery hint is missing.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: worker_run_id missing on failure path.", file=sys.stderr)
        sys.exit(1)

    print("\nSubmitting human rejection decision...")
    state_fail = graph.resume_task(
        task_id=task_fail_id,
        decision="reject",
        actor="operator",
        reviewer_note="Failed worker execution confirmed.",
        state_patch={},
    )
    _assert_state(state_fail, "failed", "complete")
    print("Failure path verified successfully!")

    for tid in [task_succeed_id, task_fail_id]:
        p = TASKS_DIR / f"{tid}.json"
        if p.exists():
            p.unlink()

    print("\nHonest Runtime Status:")
    print(f"- LangGraph available: {graph.langgraph_available}")
    print(f"- SQLite checkpoint file: {CHECKPOINT_DB_PATH}")
    print(f"- SQLite checkpoint exists: {checkpoint_file_exists()}")
    print("=== Verification Completed Successfully ===")


if __name__ == "__main__":
    main()
