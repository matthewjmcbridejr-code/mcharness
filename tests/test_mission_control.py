"""Unit tests for mission control metrics and aggregation."""

from __future__ import annotations

from src.warden.mission_control import (
    build_idle_mission,
    build_mission_header,
    build_plan_step_rows,
    build_safety_payload,
    calculate_mission_status,
    calculate_progress_percent,
    estimate_eta_seconds,
    map_step_ui_status,
)
from src.warden.captain_plans import persist_plan


def _sample_plan():
    return {
        "plan_id": "plan_metrics01",
        "goal": "Metrics test",
        "title": "Metrics plan",
        "summary": "Progress metrics.",
        "repo_id": "mcharness-public-export",
        "status": "active",
        "current_step_id": "step_1",
        "steps": [
            {
                "step_id": "step_1",
                "order": 1,
                "title": "Inspect",
                "agent_id": "codex_cli",
                "status": "passed",
                "created_at": "2026-06-09T10:00:00+00:00",
                "updated_at": "2026-06-09T10:05:00+00:00",
                "run_id": "run_1",
            },
            {
                "step_id": "step_2",
                "order": 2,
                "title": "Implement",
                "agent_id": "codex_cli",
                "status": "dispatched",
                "created_at": "2026-06-09T10:06:00+00:00",
                "updated_at": "2026-06-09T10:07:00+00:00",
                "run_id": "run_2",
            },
        ],
    }


def test_idle_mission_state():
    mission = build_idle_mission()
    assert mission["status"] == "idle"
    assert mission["mission_id"] is None
    assert mission["progress_percent"] == 0


def test_progress_and_status_for_active_plan(tmp_path):
    plan = persist_plan(
        tmp_path,
        goal="Metrics test",
        repo_id="mcharness-public-export",
        plan_data=_sample_plan(),
    )
    step_rows = build_plan_step_rows(plan, tmp_path, agents_by_id={})
    assert calculate_progress_percent(step_rows) == 50
    assert calculate_mission_status(plan, step_rows) == "running"
    mission = build_mission_header(plan, step_rows)
    assert mission["mission_id"] == "plan_metrics01"
    assert mission["current_step_id"] == "step_1"
    assert mission["progress_percent"] == 50


def test_gate_blocked_mission_status(tmp_path):
    from src.warden.proof_gates import create_proof_gate

    plan = persist_plan(
        tmp_path,
        goal="Blocked test",
        repo_id="mcharness-public-export",
        plan_data=_sample_plan(),
    )
    from src.warden.proof_gates import decide_proof_gate

    gate = create_proof_gate(
        tmp_path,
        run_id="run_2",
        plan_id="plan_metrics01",
        step_id="step_2",
        title="Block me",
        summary="Hold.",
    )
    decide_proof_gate(tmp_path, gate["gate_id"], decision="block", decided_by="operator", decision_reason="Unsafe.")
    step_rows = build_plan_step_rows(plan, tmp_path, agents_by_id={})
    assert calculate_mission_status(plan, step_rows) == "blocked"
    blocked_row = next(row for row in step_rows if row["step_id"] == "step_2")
    assert blocked_row["status"] == "blocked"


def test_completed_mission_status(tmp_path):
    plan_data = _sample_plan()
    for step in plan_data["steps"]:
        step["status"] = "passed"
    plan = persist_plan(tmp_path, goal="Done", repo_id="repo", plan_data=plan_data)
    step_rows = build_plan_step_rows(plan, tmp_path, agents_by_id={})
    assert calculate_mission_status(plan, step_rows) == "completed"
    assert calculate_progress_percent(step_rows) == 100


def test_eta_null_without_completed_durations(tmp_path):
    plan = persist_plan(tmp_path, goal="No eta", repo_id="repo", plan_data=_sample_plan())
    step_rows = build_plan_step_rows(plan, tmp_path, agents_by_id={})
    assert estimate_eta_seconds(step_rows) is None


def test_map_step_ui_status_respects_gate_state():
    step = {"status": "dispatched"}
    assert map_step_ui_status(step, "blocked") == "blocked"
    assert map_step_ui_status(step, "needs_more_evidence") == "needs_more_evidence"
    assert map_step_ui_status(step, "none") == "in_progress"


def test_safety_payload_public_runner_disabled():
    payload = build_safety_payload(
        codex_runner_ready=False,
        tmux_runner_enabled=False,
        codex_runner_enabled=False,
        jules_runnable=False,
    )
    assert payload["public_runner_enabled"] is False
    assert payload["arbitrary_shell_input"] is False
    assert payload["jules_runnable"] is False
    assert payload["secrets_exposed"] is False
    assert any(item["key"] == "public_runner" for item in payload["items"])