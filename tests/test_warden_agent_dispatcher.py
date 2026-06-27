"""Tests for Warden Agent Dispatcher."""
import json
import tempfile
from pathlib import Path

import pytest

from src.warden.agent_dispatcher import (
    AgentDispatcher,
    build_prompt_file,
    _iter_tasks_by_status,
    LOG_DIR,
)
from src.warden.risk_gate import RiskGateViolation


@pytest.fixture
def tmp_board(tmp_path, monkeypatch):
    """Create a fake board root and monkeypatch BOARD_ROOT."""
    board = tmp_path / "_mctable"
    (board / "tasks" / "queued").mkdir(parents=True)
    (board / "tasks" / "claimed").mkdir(parents=True)
    (board / "tasks" / "completed").mkdir(parents=True)
    (board / "tasks" / "failed").mkdir(parents=True)
    (board / "activity").mkdir(parents=True)
    import src.warden.agent_dispatcher as mod
    monkeypatch.setattr(mod, "BOARD_ROOT", board)
    monkeypatch.setattr(mod, "LOG_DIR", tmp_path / "runs")
    return board


@pytest.fixture
def sample_task():
    return {
        "task_id": "test-task-001",
        "title": "Test Task",
        "description": "Do something safe.",
        "agent": "cl",
        "priority": "medium",
        "status": "queued",
    }


def _write_task(board: Path, status: str, task: dict):
    path = board / "tasks" / status / f"{task['task_id']}.json"
    path.write_text(json.dumps(task))
    return path


def test_build_prompt_file(tmp_path, monkeypatch):
    import src.warden.agent_dispatcher as mod
    monkeypatch.setattr(mod, "LOG_DIR", tmp_path)
    task = {"task_id": "t1", "title": "T1", "description": "desc", "agent": "cl"}
    path = build_prompt_file(task)
    assert path.exists()
    content = path.read_text()
    assert "Warden Dispatched Task" in content
    assert "T1" in content
    assert "Required Closeout" in content
    assert "proof" in content


def test_dry_run_dispatches_without_launching(tmp_board, sample_task, monkeypatch):
    import src.warden.agent_dispatcher as mod
    monkeypatch.setattr(mod, "LOG_DIR", tmp_board.parent / "runs")
    path = _write_task(tmp_board, "queued", sample_task)
    dispatcher = AgentDispatcher(
        config={
            "enabled": True,
            "poll_interval_seconds": 1,
            "default_timeout_seconds": 30,
            "log_dir": str(tmp_board.parent / "runs"),
            "allowed_repo_roots": [],
            "agents": {"cl": {"enabled": True, "command_template": ["cl", "--prompt-file", "{prompt_file}"]}},
        },
        dry_run=True,
    )
    result = dispatcher.dispatch_task(sample_task, path)
    assert result.success
    assert "dry-run" in result.summary
    # Task should NOT be claimed (dry-run skips claim)
    assert not (tmp_board / "tasks" / "claimed" / "test-task-001.json").exists()


def test_ignores_disabled_agent(tmp_board, sample_task, monkeypatch):
    import src.warden.agent_dispatcher as mod
    monkeypatch.setattr(mod, "LOG_DIR", tmp_board.parent / "runs")
    path = _write_task(tmp_board, "queued", sample_task)
    dispatcher = AgentDispatcher(
        config={
            "enabled": True,
            "poll_interval_seconds": 1,
            "default_timeout_seconds": 30,
            "log_dir": str(tmp_board.parent / "runs"),
            "allowed_repo_roots": [],
            "agents": {"cl": {"enabled": False, "command_template": ["cl", "--prompt-file", "{prompt_file}"]}},
        },
        dry_run=True,
    )
    result = dispatcher.dispatch_task(sample_task, path)
    assert not result.success
    assert "No enabled agent" in result.summary


def test_skips_task_outside_allowed_paths(tmp_board, monkeypatch):
    import src.warden.agent_dispatcher as mod
    monkeypatch.setattr(mod, "LOG_DIR", tmp_board.parent / "runs")
    task = {
        "task_id": "bad-path-task",
        "title": "Bad",
        "description": "desc",
        "agent": "cl",
        "repo": "/etc/forbidden",
        "status": "queued",
    }
    path = _write_task(tmp_board, "queued", task)
    dispatcher = AgentDispatcher(
        config={
            "enabled": True,
            "poll_interval_seconds": 1,
            "default_timeout_seconds": 30,
            "log_dir": str(tmp_board.parent / "runs"),
            "allowed_repo_roots": ["/home/matt/workspaces"],
            "agents": {"cl": {"enabled": True, "command_template": ["cl", "--prompt-file", "{prompt_file}"]}},
        },
        dry_run=True,
    )
    result = dispatcher.dispatch_task(task, path)
    assert not result.success
    assert "allowed" in result.summary.lower()


def test_poll_once_returns_results(tmp_board, sample_task, monkeypatch):
    import src.warden.agent_dispatcher as mod
    monkeypatch.setattr(mod, "BOARD_ROOT", tmp_board)
    monkeypatch.setattr(mod, "LOG_DIR", tmp_board.parent / "runs")
    _write_task(tmp_board, "queued", sample_task)
    dispatcher = AgentDispatcher(
        config={
            "enabled": True,
            "poll_interval_seconds": 1,
            "default_timeout_seconds": 30,
            "log_dir": str(tmp_board.parent / "runs"),
            "allowed_repo_roots": [],
            "agents": {"cl": {"enabled": True, "command_template": ["cl", "--prompt-file", "{prompt_file}"]}},
        },
        dry_run=True,
    )
    results = dispatcher.poll_once()
    assert len(results) == 1
    assert results[0].task_id == "test-task-001"


def test_command_not_found_returns_failure(tmp_board, monkeypatch):
    import src.warden.agent_dispatcher as mod
    monkeypatch.setattr(mod, "BOARD_ROOT", tmp_board)
    monkeypatch.setattr(mod, "LOG_DIR", tmp_board.parent / "runs")
    task = {
        "task_id": "missing-cmd",
        "title": "Missing Cmd",
        "description": "desc",
        "agent": "cl",
        "status": "queued",
    }
    path = _write_task(tmp_board, "queued", task)
    dispatcher = AgentDispatcher(
        config={
            "enabled": True,
            "poll_interval_seconds": 1,
            "default_timeout_seconds": 5,
            "log_dir": str(tmp_board.parent / "runs"),
            "allowed_repo_roots": [],
            "agents": {"cl": {"enabled": True, "command_template": ["__no_such_cmd__", "--prompt-file", "{prompt_file}"]}},
        },
        dry_run=False,
    )
    result = dispatcher.dispatch_task(task, path)
    assert not result.success
    assert "not found" in result.summary or "exit" in result.summary
