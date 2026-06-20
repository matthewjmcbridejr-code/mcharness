"""Unit tests for runner session inventory and cleanup helpers."""

from __future__ import annotations

import subprocess

import pytest
from fastapi import HTTPException

from src.warden.runner_sessions import (
    BLOCKED_SESSION_NAMES,
    RUNNER_SESSION_PREFIX,
    assert_runner_session_capacity,
    build_runner_session_inventory,
    cleanup_runner_sessions,
    is_manageable_runner_session,
    linked_run_id_from_session_name,
    parse_tmux_list_panes_output,
    parse_tmux_list_sessions_output,
    sanitize_command_name,
)


def test_is_manageable_runner_session_filters_names():
    assert is_manageable_runner_session("mch_run_run_abc123")
    assert not is_manageable_runner_session("mch_abc123")
    assert not is_manageable_runner_session("main")
    assert not is_manageable_runner_session("grok")
    for blocked in BLOCKED_SESSION_NAMES:
        assert not is_manageable_runner_session(blocked)
    assert is_manageable_runner_session(f"{RUNNER_SESSION_PREFIX}dev")


def test_linked_run_id_from_session_name():
    assert linked_run_id_from_session_name("mch_run_run_deadbeef") == "run_deadbeef"
    assert linked_run_id_from_session_name("mch_run_other") is None


def test_parse_tmux_list_sessions_output():
    stdout = "mch_run_run_a\t1710000000\t1710000100\t0\nmain\t1710000000\t1710000100\t1\n"
    rows = parse_tmux_list_sessions_output(stdout)
    assert len(rows) == 2
    assert rows[0]["session_name"] == "mch_run_run_a"


def test_parse_tmux_list_panes_output():
    pane = parse_tmux_list_panes_output("12345\tnode\tmcharness-public-export\n")
    assert pane["pane_pid"] == "12345"
    assert pane["pane_current_command"] == "node"
    assert pane["pane_title"] == "mcharness-public-export"


def test_sanitize_command_name_redacts_tokens():
    assert sanitize_command_name("node /path/to/script") == "node"
    safe, _ = __import__("src.warden.run_history", fromlist=["redact_secrets"]).redact_secrets("codex --api-key sk-or-secret")
    assert "sk-or" not in sanitize_command_name("codex --api-key sk-or-secret")


def test_build_inventory_ignores_non_matching_sessions(tmp_path):
    calls: list[tuple[str, ...]] = []

    def fake_safe_cmd(cmd, timeout=2.5, cwd=None):
        calls.append(tuple(cmd))
        if cmd[:2] == ["tmux", "list-sessions"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\t1\t2\t0\nmch_run_run_one\t100\t200\t0\n", stderr="")
        if cmd[:3] == ["tmux", "list-panes", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="99\tnode\trepo\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="err")

    inventory = build_runner_session_inventory(
        tmp_path,
        safe_cmd=fake_safe_cmd,
        runner_state_root=tmp_path / "runners",
        include_details=True,
        stale_after_seconds=10,
    )
    assert inventory["total_runner_sessions"] == 1
    assert inventory["items"][0]["session_name"] == "mch_run_run_one"
    assert inventory["items"][0]["command"] == "node"
    assert any(call[:2] == ("tmux", "list-sessions") for call in calls)


def test_cleanup_dry_run_kills_nothing(tmp_path):
    killed_names: list[str] = []

    def fake_safe_cmd(cmd, timeout=2.5, cwd=None):
        if cmd[:2] == ["tmux", "list-sessions"]:
            old = 1
            return subprocess.CompletedProcess(cmd, 0, stdout=f"mch_run_run_old\t{old}\t{old}\t0\n", stderr="")
        if cmd[:3] == ["tmux", "list-panes", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="1\tnode\ttitle\n", stderr="")
        if cmd[:2] == ["tmux", "kill-session"]:
            killed_names.append(cmd[3])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    result = cleanup_runner_sessions(
        tmp_path,
        safe_cmd=fake_safe_cmd,
        runner_state_root=tmp_path / "runners",
        confirm=False,
        stale_after_seconds=1,
    )
    assert result["dry_run"] is True
    assert result["candidates"]
    assert result["killed"] == []
    assert killed_names == []


def test_assert_runner_session_capacity_allows_below_limit(tmp_path, monkeypatch):
    import src.warden.runner_sessions as mod

    monkeypatch.setattr(
        mod,
        "build_runner_session_inventory",
        lambda *args, **kwargs: {
            "max_active_runner_sessions": 4,
            "active_runner_sessions": 3,
            "total_runner_sessions": 3,
            "stale_runner_sessions": 0,
            "items": [],
        },
    )
    assert_runner_session_capacity(tmp_path, safe_cmd=lambda *a, **k: None, runner_state_root=tmp_path / "runners")


def test_assert_runner_session_capacity_rejects_at_limit(tmp_path, monkeypatch):
    import src.warden.runner_sessions as mod

    monkeypatch.setattr(
        mod,
        "build_runner_session_inventory",
        lambda *args, **kwargs: {
            "max_active_runner_sessions": 4,
            "active_runner_sessions": 4,
            "total_runner_sessions": 4,
            "stale_runner_sessions": 0,
            "items": [],
        },
    )
    with pytest.raises(HTTPException) as exc:
        assert_runner_session_capacity(tmp_path, safe_cmd=lambda *a, **k: None, runner_state_root=tmp_path / "runners")
    assert exc.value.status_code == 409
    assert "Runner session limit reached" in str(exc.value.detail)


def test_cleanup_confirm_kills_only_stale_manageable_sessions(tmp_path):
    killed: list[str] = []

    def fake_safe_cmd(cmd, timeout=2.5, cwd=None):
        if cmd[:2] == ["tmux", "list-sessions"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="mch_run_run_stale\t1\t1\t0\nmain\t1\t1\t0\nmch_run_run_active\t1\t1\t0\n",
                stderr="",
            )
        if cmd[:3] == ["tmux", "list-panes", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="1\tnode\ttitle\n", stderr="")
        if cmd[:2] == ["tmux", "kill-session"]:
            killed.append(cmd[3])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    result = cleanup_runner_sessions(
        tmp_path,
        safe_cmd=fake_safe_cmd,
        runner_state_root=tmp_path / "runners",
        confirm=True,
        stale_after_seconds=1,
    )
    assert result["dry_run"] is False
    assert "mch_run_run_stale" in result["killed"]
    assert "main" not in killed
    assert all(name.startswith("mch_run_") for name in killed)