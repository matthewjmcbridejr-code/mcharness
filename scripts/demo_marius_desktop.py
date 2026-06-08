from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from src.marius_desktop.api import get_capabilities, get_status
from src.marius_desktop.captain import CAPTAIN_ROOT
from src.marius_desktop.graph import CHECKPOINT_DB_PATH, MCTABLE_ROOT, TASKS_DIR, McTableTaskGraph, checkpoint_file_exists
from src.marius_desktop.worker import WorkerStub
from src.server.api import app

FAKE_WORKER_COMMANDS = [
    "fake-worker-success",
    "fake-worker-fail",
    "fake-worker-sleep",
]


def _print_capabilities() -> None:
    print("\nCapabilities:")
    for cap in get_capabilities():
        print(f"- {cap.name}: {cap.status} | {cap.summary}")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _cleanup_task(task_id: str) -> None:
    task_path = TASKS_DIR / f"{task_id}.json"
    if task_path.exists():
        task_path.unlink()


def _cleanup_run_dir(run_id: str | None) -> None:
    if not run_id:
        return
    run_dir = MCTABLE_ROOT / "worker_runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)


def _cleanup_captain_run(run_id: str | None) -> None:
    if not run_id:
        return
    run_path = CAPTAIN_ROOT / "runs" / f"{run_id}.json"
    if run_path.exists():
        run_path.unlink()


def _demo_task(graph: McTableTaskGraph, task_id: str, command: str, title: str, description: str):
    print(f"\nCreating task '{task_id}' with command '{command}'...")
    state = graph.create_task(
        task_id=task_id,
        title=title,
        description=description,
        command=command,
        args=[],
    )
    state = graph.drive_task_to_review(task_id)
    _assert(state.status == "paused", "Expected task to pause at human review gate.")
    _assert(state.current_step == "human_review_gate", "Expected human review gate.")
    print(f"Paused at {state.current_step} with status={state.status}")
    _assert(bool(state.worker_run_id), "worker_run_id missing.")

    run = WorkerStub.get_status(state.worker_run_id)
    print(f"Worker run status: {run.status}, exit_code={run.exit_code}")
    logs = "".join(list(WorkerStub.stream_logs(state.worker_run_id)))
    print(f"Worker logs snippet:\n{logs.strip()}")
    res_file = Path(run.logs_path) / "result.json"
    print(f"Result file exists: {res_file.exists()}")
    _assert(res_file.exists(), "Expected worker result.json to exist.")

    return state


def main() -> int:
    print("=== McHarness Smoke Demo ===")
    print("Allowlisted fake-worker commands:", ", ".join(FAKE_WORKER_COMMANDS))
    status = get_status()
    _print_capabilities()

    print("\nService status:")
    for key, value in status.items():
        print(f"- {key}: {value}")

    _assert(status["langgraph_available"] is True, "LangGraph must be available.")
    _assert(status["sqlite_checkpointing_available"] is True, "SQLite checkpointing must be available.")
    checkpoint_probe = checkpoint_file_exists()
    _assert(isinstance(checkpoint_probe, bool), "checkpoint probe must be callable.")

    client = TestClient(app)
    graph = McTableTaskGraph()

    success_id = f"demo-success-{uuid.uuid4().hex[:8]}"
    fail_id = f"demo-fail-{uuid.uuid4().hex[:8]}"
    captain_run_id = None
    success_state = None
    fail_state = None

    try:
        success_state = _demo_task(
            graph,
            success_id,
            "fake-worker-success",
            "Demo success task",
            "Prove the success path for the local demo smoke script.",
        )
        print("\nSubmitting human approval decision...")
        success_state = graph.resume_task(
            task_id=success_id,
            decision="approve",
            actor="operator",
            reviewer_note="Looks good in the smoke demo.",
            state_patch={},
        )
        _assert(success_state.status == "completed", "Success path should complete.")
        _assert(success_state.proof_status == "approved", "Success path should approve proof.")
        print("Success path verified successfully!")

        fail_state = _demo_task(
            graph,
            fail_id,
            "fake-worker-fail",
            "Demo fail task",
            "Prove the failure path for the local demo smoke script.",
        )
        _assert(bool(fail_state.recovery_hint), "Failure recovery hint is missing.")
        print(f"Recovery Hint (Deliberate fail): {fail_state.recovery_hint}")

        print("\nSubmitting human rejection decision...")
        fail_state = graph.resume_task(
            task_id=fail_id,
            decision="reject",
            actor="operator",
            reviewer_note="Failed worker execution confirmed.",
            state_patch={},
        )
        _assert(fail_state.status == "failed", "Failure path should end as failed.")
        _assert(fail_state.proof_status == "rejected", "Failure path should reject proof.")
        print("Failure path verified successfully!")

        bad_task = {
            "task_id": f"demo-bad-{uuid.uuid4().hex[:8]}",
            "title": "Unknown command demo",
            "description": "Reject an unknown command through the API.",
            "command": "rm -rf /",
            "args": [],
        }
        bad_response = client.post("/api/marius/tasks", json=bad_task)
        _assert(bad_response.status_code == 400, "Unknown command should be rejected through the API.")
        print("Unknown command rejected through API: yes")

        captain_response = client.get("/api/marius/captain/runs")
        _assert(captain_response.status_code == 200, "Captain Mode API must be available.")
        captain_created = client.post(
            "/api/marius/captain/runs",
            json={
                "objective": "Demo Captain Run",
                "next_action": "inspect",
                "planned_acceptance_commands": [
                    "python -m pytest -q tests/test_marius_desktop_demo_script.py",
                ],
            },
        )
        _assert(captain_created.status_code == 200, "Captain run creation failed.")
        captain_run = captain_created.json()
        captain_run_id = captain_run["run_id"]
        print(f"Captain run created: {captain_run_id}")

        evidence_response = client.post(
            f"/api/marius/captain/runs/{captain_run_id}/evidence",
            json={
                "summary": "Demo evidence record",
                "details": "Captain Mode stores evidence as local text records.",
                "captured_by": "captain",
                "artifacts": ["docs/demo_script.md"],
            },
        )
        _assert(evidence_response.status_code == 200, "Captain evidence append failed.")
        print("Captain evidence added: yes")

        gate_response = client.post(
            f"/api/marius/captain/runs/{captain_run_id}/gate",
            json={
                "kind": "review",
                "reason": "Demo hard gate",
                "triggered_by": "smoke-script",
            },
        )
        _assert(gate_response.status_code == 200, "Captain gate creation failed.")
        print("Captain hard gate triggered: yes")

        blocked_response = client.post(
            f"/api/marius/captain/runs/{captain_run_id}/next",
            json={
                "next_action": "continue",
                "planned_acceptance_commands": ["fake-worker-success"],
            },
        )
        _assert(blocked_response.status_code == 409, "Captain next action should be blocked by the hard gate.")
        print("Captain next action blocked by hard gate: yes")

        exec_response = client.post(
            f"/api/marius/captain/runs/{captain_run_id}/next",
            json={
                "next_action": "continue",
                "planned_acceptance_commands": ["fake-worker-success"],
                "command_execution_request": True,
            },
        )
        _assert(exec_response.status_code == 501, "Command execution requests must be blocked/not_implemented.")
        print("Command execution request blocked/not_implemented: yes")

        print("\nHonest Runtime Status:")
        print(f"- LangGraph available: {status['langgraph_available']}")
        print(f"- SQLite checkpoint file: {CHECKPOINT_DB_PATH}")
        print(f"- SQLite checkpoint exists: {checkpoint_file_exists()}")
        print("=== Smoke Demo Completed Successfully ===")
        return 0
    finally:
        _cleanup_task(success_id)
        _cleanup_task(fail_id)
        _cleanup_run_dir(success_state.worker_run_id if success_state else None)
        _cleanup_run_dir(fail_state.worker_run_id if fail_state else None)
        _cleanup_captain_run(captain_run_id)


if __name__ == "__main__":
    raise SystemExit(main())
