import pytest
import shutil
import time
from src.marius_desktop.worker import WorkerStub, RUNS_DIR

@pytest.fixture(autouse=True)
def clean_worker_runs():
    if RUNS_DIR.exists():
        shutil.rmtree(RUNS_DIR)
    yield
    if RUNS_DIR.exists():
        shutil.rmtree(RUNS_DIR)

def test_happy_path_success():
    run_id = WorkerStub.start_run("agent-1", "task-1", "fake-worker-success", [])
    assert run_id is not None
    
    # Wait for completion (it is fast since it's success)
    time.sleep(0.5)
    
    run_status = WorkerStub.get_status(run_id)
    assert run_status.status == "success"
    assert run_status.exit_code == 0
    assert run_status.finished_at is not None

    # Check state file location
    run_dir = RUNS_DIR / run_id
    assert run_dir.exists()
    assert (run_dir / "run.json").exists()
    assert (run_dir / "result.json").exists()

    # Verify result conforms to schema
    with open(run_dir / "result.json", "r", encoding="utf-8") as f:
        import json
        result = json.load(f)
    assert result["status"] == "success"
    assert result["summary"] == "Fake worker succeeded."
    assert result["recovery_hint"] is None

def test_failure_path_recovery_hint():
    run_id = WorkerStub.start_run("agent-1", "task-2", "fake-worker-fail", [])
    time.sleep(0.5)

    run_status = WorkerStub.get_status(run_id)
    assert run_status.status == "failed"
    assert run_status.exit_code == 1

    run_dir = RUNS_DIR / run_id
    with open(run_dir / "result.json", "r", encoding="utf-8") as f:
        import json
        result = json.load(f)
    assert result["status"] == "failed"
    assert "fake-worker-success" in result["recovery_hint"]

def test_unknown_command_rejected():
    with pytest.raises(ValueError):
        WorkerStub.start_run("agent-1", "task-3", "unsafe-command-here", [])

def test_status_not_running_after_exit():
    run_id = WorkerStub.start_run("agent-1", "task-4", "fake-worker-success", [])
    time.sleep(0.5)
    
    run_status = WorkerStub.get_status(run_id)
    # The process has exited, status should not be running
    assert run_status.status == "success"

def test_logs_streamed_and_persisted():
    run_id = WorkerStub.start_run("agent-1", "task-5", "fake-worker-success", [])
    time.sleep(0.5)

    logs = "".join(list(WorkerStub.stream_logs(run_id)))
    assert "Success output" in logs

    run_dir = RUNS_DIR / run_id
    assert (run_dir / "stdout.log").exists()

def test_cancel_updates_status():
    run_id = WorkerStub.start_run("agent-1", "task-6", "fake-worker-sleep", [])
    
    # Active process cancel
    WorkerStub.cancel_run(run_id)
    
    run_status = WorkerStub.get_status(run_id)
    assert run_status.status == "cancelled"
    assert run_status.exit_code == -1

    run_dir = RUNS_DIR / run_id
    with open(run_dir / "result.json", "r", encoding="utf-8") as f:
        import json
        result = json.load(f)
    assert result["status"] == "cancelled"
    assert result["recovery_hint"] == "Task cancelled by operator."

    logs = "".join(list(WorkerStub.stream_logs(run_id)))
    assert isinstance(logs, str)

def test_path_traversal_get_status():
    with pytest.raises(ValueError, match="Invalid run_id format"):
        WorkerStub.get_status("../../../etc/passwd")

def test_path_traversal_stream_logs():
    with pytest.raises(ValueError, match="Invalid run_id format"):
        list(WorkerStub.stream_logs("../../../etc/passwd"))

def test_path_traversal_cancel_run():
    with pytest.raises(ValueError, match="Invalid run_id format"):
        WorkerStub.cancel_run("../../../etc/passwd")
