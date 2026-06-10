"""Mission Control aggregation for Warden dashboard read APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_registry import list_all_agents, sanitize_agent_profile
from .captain_plans import (
    _sorted_steps,
    get_plan_record,
    list_recent_plans,
    pause_mission_plan,
    request_plan_adjustment,
)
from .proof_gates import (
    gate_status_summary_for_run,
    gate_ui_label,
    list_recent_gates,
)
from .run_history import get_run_record, list_recent_runs
from .worklog import EVENT_LABELS, list_recent_worklog

MISSION_STATUSES = frozenset({
    "idle",
    "planned",
    "running",
    "blocked",
    "needs_more_evidence",
    "completed",
    "stopped",
})

STEP_UI_STATUSES = frozenset({
    "pending",
    "in_progress",
    "completed",
    "blocked",
    "needs_more_evidence",
})

GATE_STATE_NONE = "none"
GATE_STATES = frozenset({GATE_STATE_NONE, "pending", "approved", "blocked", "needs_more_evidence"})

NEXT_MOVE_ACTIONS = frozenset({
    "develop_plan",
    "view_codex",
    "review_gate",
    "request_evidence",
    "mark_step_done",
    "none",
})

AGENT_HEALTH_STATUSES = frozenset({
    "ready",
    "disabled",
    "working",
    "idle",
    "error",
    "not_configured",
})

AGENT_MODES = frozenset({"execution", "planning_only", "disabled", "orchestrator"})

PASSED_STEP_STATUSES = frozenset({"passed", "skipped"})
IN_PROGRESS_STEP_STATUSES = frozenset({"dispatched", "running", "needs_review"})
COMPLETED_PLAN_STATUSES = frozenset({"completed"})
STOPPED_PLAN_STATUSES = frozenset({"stopped"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _duration_seconds(start: str | None, end: str | None) -> int | None:
    start_dt = _parse_iso(start)
    end_dt = _parse_iso(end)
    if start_dt is None or end_dt is None:
        return None
    delta = end_dt - start_dt
    if delta.total_seconds() < 0:
        return None
    return int(delta.total_seconds())


def gate_state_for_run(root: Path, run_id: str | None) -> str:
    if not run_id:
        return GATE_STATE_NONE
    summary = gate_status_summary_for_run(root, str(run_id))
    if not summary:
        return GATE_STATE_NONE
    return str(summary)


def map_step_ui_status(step: dict[str, Any], gate_state: str) -> str:
    raw_status = str(step.get("status") or "queued")
    if gate_state == "blocked":
        return "blocked"
    if gate_state == "needs_more_evidence":
        return "needs_more_evidence"
    if raw_status in PASSED_STEP_STATUSES:
        return "completed"
    if raw_status in IN_PROGRESS_STEP_STATUSES:
        return "in_progress"
    if raw_status in {"stopped", "failed"}:
        return "blocked"
    return "pending"


def _agent_label(agent_id: str, agents_by_id: dict[str, dict[str, Any]]) -> str:
    agent = agents_by_id.get(agent_id)
    if agent:
        return str(agent.get("name") or agent_id)
    if agent_id == "captain":
        return "Captain"
    return agent_id


def build_plan_step_rows(
    plan: dict[str, Any],
    root: Path,
    *,
    agents_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in _sorted_steps(plan.get("steps") or []):
        step_id = str(step.get("step_id") or "")
        run_id = step.get("run_id")
        gate_state = gate_state_for_run(root, str(run_id) if run_id else None)
        run = get_run_record(root, str(run_id)) if run_id else None
        duration = _duration_seconds(
            (run or {}).get("started_at") or step.get("created_at"),
            (run or {}).get("ended_at") or step.get("updated_at"),
        )
        rows.append(
            {
                "step_id": step_id,
                "number": int(step.get("order") or 0),
                "title": step.get("title"),
                "status": map_step_ui_status(step, gate_state),
                "agent_id": step.get("agent_id") or "codex_cli",
                "agent_label": _agent_label(str(step.get("agent_id") or "codex_cli"), agents_by_id),
                "run_id": run_id,
                "gate_state": gate_state,
                "duration_seconds": duration,
            }
        )
    return rows


def calculate_progress_percent(step_rows: list[dict[str, Any]]) -> int:
    if not step_rows:
        return 0
    completed = sum(1 for row in step_rows if row.get("status") == "completed")
    return int(round((completed / len(step_rows)) * 100))


def calculate_mission_status(
    plan: dict[str, Any] | None,
    step_rows: list[dict[str, Any]],
) -> str:
    if plan is None:
        return "idle"
    plan_status = str(plan.get("status") or "active")
    if plan_status in STOPPED_PLAN_STATUSES:
        return "stopped"
    if any(row.get("status") == "blocked" for row in step_rows):
        return "blocked"
    if any(row.get("status") == "needs_more_evidence" for row in step_rows):
        return "needs_more_evidence"
    if step_rows and all(row.get("status") == "completed" for row in step_rows):
        return "completed"
    if any(row.get("status") == "in_progress" for row in step_rows):
        return "running"
    has_run = any(row.get("run_id") for row in step_rows)
    if has_run:
        return "running"
    if plan is not None:
        return "planned"
    return "idle"


def estimate_eta_seconds(step_rows: list[dict[str, Any]]) -> int | None:
    completed_durations = [
        int(row["duration_seconds"])
        for row in step_rows
        if row.get("status") == "completed" and isinstance(row.get("duration_seconds"), int)
    ]
    remaining = [row for row in step_rows if row.get("status") not in {"completed"}]
    if len(completed_durations) < 1 or not remaining:
        return None
    average = sum(completed_durations) / len(completed_durations)
    return int(round(average * len(remaining)))


def select_active_plan(root: Path, *, history_enabled: bool) -> dict[str, Any] | None:
    if not history_enabled:
        return None
    plans = list_recent_plans(root, limit=20)
    if not plans:
        return None
    for plan in plans:
        if str(plan.get("status") or "") == "active":
            return get_plan_record(root, str(plan.get("plan_id") or ""))
    first_id = str(plans[0].get("plan_id") or "")
    return get_plan_record(root, first_id) if first_id else None


def build_idle_mission() -> dict[str, Any]:
    return {
        "mission_id": None,
        "title": "No active mission",
        "status": "idle",
        "started_at": None,
        "updated_at": None,
        "progress_percent": 0,
        "eta_seconds": None,
        "current_step_id": None,
        "current_step_title": None,
        "current_agent_id": None,
        "summary": "Create a Captain plan to start a supervised mission.",
    }


def build_mission_header(
    plan: dict[str, Any] | None,
    step_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if plan is None:
        return build_idle_mission()
    current_step_id = plan.get("current_step_id")
    current_row = next((row for row in step_rows if row.get("step_id") == current_step_id), None)
    if current_row is None and step_rows:
        current_row = step_rows[0]
    status = calculate_mission_status(plan, step_rows)
    return {
        "mission_id": plan.get("plan_id"),
        "title": plan.get("title") or plan.get("goal") or "Captain mission",
        "status": status,
        "started_at": plan.get("created_at"),
        "updated_at": plan.get("updated_at"),
        "progress_percent": calculate_progress_percent(step_rows),
        "eta_seconds": estimate_eta_seconds(step_rows),
        "current_step_id": current_row.get("step_id") if current_row else None,
        "current_step_title": current_row.get("title") if current_row else None,
        "current_agent_id": current_row.get("agent_id") if current_row else None,
        "summary": plan.get("summary") or plan.get("goal") or "",
    }


def build_proof_gates_payload(root: Path, *, history_enabled: bool) -> dict[str, Any]:
    if not history_enabled:
        return {
            "summary": {
                "total": 0,
                "passed": 0,
                "pending": 0,
                "blocked": 0,
                "needs_more_evidence": 0,
            },
            "items": [],
        }
    gates = list_recent_gates(root, limit=30)
    summary = {
        "total": len(gates),
        "passed": sum(1 for gate in gates if gate.get("status") == "approved"),
        "pending": sum(1 for gate in gates if gate.get("status") == "pending"),
        "blocked": sum(1 for gate in gates if gate.get("status") == "blocked"),
        "needs_more_evidence": sum(1 for gate in gates if gate.get("status") == "needs_more_evidence"),
    }
    items = [
        {
            "gate_id": gate.get("gate_id"),
            "title": gate.get("title"),
            "status": gate.get("status"),
            "label": gate_ui_label(gate.get("status")),
            "run_id": gate.get("run_id"),
            "plan_id": gate.get("plan_id"),
            "step_id": gate.get("step_id"),
            "created_at": gate.get("created_at"),
            "decided_at": gate.get("decided_at"),
        }
        for gate in gates
    ]
    return {"summary": summary, "items": items}


def _agent_working_state(agent_id: str, plan: dict[str, Any] | None, runs: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not plan:
        return None, None
    for step in _sorted_steps(plan.get("steps") or []):
        if str(step.get("agent_id") or "") != agent_id:
            continue
        if str(step.get("status") or "") in IN_PROGRESS_STEP_STATUSES and step.get("run_id"):
            return str(step.get("run_id")), str(step.get("step_id") or "")
    for run in runs:
        if str(run.get("agent_id") or "") == agent_id and str(run.get("status") or "") in {"running", "dispatched"}:
            return str(run.get("run_id") or ""), None
    return None, None


def map_agent_health_status(agent: dict[str, Any], *, active_run_id: str | None) -> str:
    if not agent.get("enabled", True):
        return "disabled"
    connection = str(agent.get("connection_status") or "")
    raw_status = str(agent.get("status") or "")
    if connection == "not_configured":
        return "not_configured"
    if raw_status == "error":
        return "error"
    if active_run_id:
        return "working"
    if agent.get("runnable"):
        return "ready"
    if raw_status in {"ready", "connected"}:
        return "idle"
    return "disabled"


def map_agent_mode(agent: dict[str, Any]) -> str:
    adapter = str(agent.get("adapter") or "")
    if adapter == "jules_remote":
        return "planning_only"
    if agent.get("runnable"):
        return "execution"
    return "disabled"


def build_agent_health_summary(agent: dict[str, Any], *, active_run_id: str | None) -> str:
    name = str(agent.get("name") or agent.get("id") or "Agent")
    mode = map_agent_mode(agent)
    status = map_agent_health_status(agent, active_run_id=active_run_id)
    if agent.get("id") == "captain":
        return "Captain orchestrator is configured and ready."
    if mode == "planning_only":
        return f"{name} is connected for planning only."
    if status == "working":
        return f"{name} is working on an active run."
    if status == "ready":
        return f"{name} is ready on the private runner."
    if status == "disabled":
        return f"{name} is disabled on this service."
    if status == "not_configured":
        return f"{name} is not configured."
    return f"{name} status: {status}."


def build_agents_health_items(
    root: Path,
    *,
    codex_runner_ready: bool,
    private_only: bool,
    plan: dict[str, Any] | None,
    captain_configured: bool,
) -> list[dict[str, Any]]:
    agents = list_all_agents(root, codex_runner_ready=codex_runner_ready, private_only=private_only)
    runs = list_recent_runs(root, limit=20) if codex_runner_ready else []
    items: list[dict[str, Any]] = []
    if captain_configured:
        items.append(
            {
                "id": "captain",
                "name": "Captain",
                "kind": "orchestrator",
                "status": "ready",
                "connection_status": "configured",
                "runnable": False,
                "private_only": True,
                "mode": "orchestrator",
                "last_checked_at": _now_iso(),
                "active_run_id": None,
                "active_step_id": plan.get("current_step_id") if plan else None,
                "summary": "Captain orchestrator is configured and ready.",
            }
        )
    for agent in agents:
        clean = sanitize_agent_profile(agent)
        agent_id = str(clean.get("id") or "")
        active_run_id, active_step_id = _agent_working_state(agent_id, plan, runs)
        items.append(
            {
                "id": agent_id,
                "name": clean.get("name"),
                "kind": clean.get("kind"),
                "status": map_agent_health_status(clean, active_run_id=active_run_id),
                "connection_status": clean.get("connection_status"),
                "runnable": bool(clean.get("runnable")),
                "private_only": bool(clean.get("private_only", True)),
                "mode": map_agent_mode(clean),
                "last_checked_at": clean.get("last_checked_at") or clean.get("updated_at"),
                "active_run_id": active_run_id,
                "active_step_id": active_step_id,
                "summary": build_agent_health_summary(clean, active_run_id=active_run_id),
            }
        )
    return items


def build_agents_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "ready": sum(1 for item in items if item.get("status") == "ready"),
        "working": sum(1 for item in items if item.get("status") == "working"),
        "idle": sum(1 for item in items if item.get("status") == "idle"),
        "blocked": sum(1 for item in items if item.get("status") in {"blocked", "disabled", "error"}),
    }


def build_safety_payload(
    *,
    codex_runner_ready: bool,
    tmux_runner_enabled: bool,
    codex_runner_enabled: bool,
    jules_runnable: bool,
) -> dict[str, Any]:
    public_runner_enabled = codex_runner_ready is False and tmux_runner_enabled is False and codex_runner_enabled is False
    # Public service: runners disabled. Private: controlled enablement.
    private_runner_enabled = codex_runner_ready
    items = [
        {
            "key": "public_runner",
            "label": "Public runner",
            "status": "disabled" if not codex_runner_ready else "controlled",
            "severity": "good",
            "summary": (
                "Public execution is disabled."
                if not codex_runner_ready
                else "Public-facing service is not used for execution."
            ),
        },
        {
            "key": "private_runner",
            "label": "Private runner",
            "status": "active" if private_runner_enabled else "disabled",
            "severity": "info" if private_runner_enabled else "good",
            "summary": (
                "Private Codex dispatch is enabled on this service."
                if private_runner_enabled
                else "Private Codex dispatch is disabled on this service."
            ),
        },
        {
            "key": "arbitrary_shell",
            "label": "Arbitrary shell input",
            "status": "disabled",
            "severity": "good",
            "summary": "Arbitrary shell input is disabled.",
        },
        {
            "key": "jules_execution",
            "label": "Jules execution",
            "status": "planning_only",
            "severity": "good",
            "summary": "Jules is connected but not executable.",
        },
        {
            "key": "secret_exposure",
            "label": "Secret exposure",
            "status": "none",
            "severity": "good",
            "summary": "API responses redact secrets and sensitive patterns.",
        },
    ]
    labels = [item["label"] for item in items]
    return {
        "secure": not jules_runnable and not public_runner_enabled,
        "public_runner_enabled": False,
        "private_runner_enabled": private_runner_enabled,
        "arbitrary_shell_input": False,
        "jules_runnable": False,
        "secrets_exposed": False,
        "labels": labels,
        "items": items,
    }


def build_next_move(
    mission: dict[str, Any],
    step_rows: list[dict[str, Any]],
    *,
    codex_runner_ready: bool,
    captain_configured: bool,
) -> dict[str, Any]:
    status = str(mission.get("status") or "idle")
    current_step_id = mission.get("current_step_id")
    current_row = next((row for row in step_rows if row.get("step_id") == current_step_id), None)

    if status == "idle":
        return {
            "label": "Develop a plan",
            "description": "Captain has no active mission. Create a supervised plan to begin.",
            "action": "develop_plan",
            "target": {},
        }
    if status == "stopped":
        return {
            "label": "Mission paused",
            "description": "The mission is stopped. Review the timeline or develop a new plan.",
            "action": "none",
            "target": {"mission_id": mission.get("mission_id")},
        }
    if status == "completed":
        return {
            "label": "Mission complete",
            "description": "All Captain steps are complete. Review evidence or start a new mission.",
            "action": "none",
            "target": {"mission_id": mission.get("mission_id")},
        }
    if current_row and current_row.get("gate_state") == "pending":
        return {
            "label": "Review proof gate",
            "description": "A proof gate is pending. Review evidence and decide before advancing.",
            "action": "review_gate",
            "target": {
                "mission_id": mission.get("mission_id"),
                "step_id": current_row.get("step_id"),
                "run_id": current_row.get("run_id"),
            },
        }
    if current_row and current_row.get("gate_state") == "needs_more_evidence":
        return {
            "label": "Request more evidence",
            "description": "The current step needs more evidence before it can be marked done.",
            "action": "request_evidence",
            "target": {
                "mission_id": mission.get("mission_id"),
                "step_id": current_row.get("step_id"),
                "run_id": current_row.get("run_id"),
            },
        }
    if current_row and current_row.get("gate_state") == "approved":
        return {
            "label": "Mark step done",
            "description": "Proof gate approved. Mark the current step done manually when ready.",
            "action": "mark_step_done",
            "target": {
                "mission_id": mission.get("mission_id"),
                "step_id": current_row.get("step_id"),
            },
        }
    if current_row and current_row.get("status") == "in_progress":
        return {
            "label": "View Codex run",
            "description": "A step is in progress. Monitor the active Codex run and capture evidence.",
            "action": "view_codex",
            "target": {
                "mission_id": mission.get("mission_id"),
                "step_id": current_row.get("step_id"),
                "run_id": current_row.get("run_id"),
            },
        }
    if captain_configured and codex_runner_ready and current_row:
        return {
            "label": "Deploy current step",
            "description": "The current step is ready for manual Codex dispatch.",
            "action": "view_codex",
            "target": {
                "mission_id": mission.get("mission_id"),
                "step_id": current_row.get("step_id"),
            },
        }
    return {
        "label": "Review mission",
        "description": "Review the current mission state and choose the next manual action.",
        "action": "none",
        "target": {"mission_id": mission.get("mission_id")},
    }


def _worklog_items_with_labels(root: Path, *, history_enabled: bool, limit: int = 50) -> list[dict[str, Any]]:
    if not history_enabled:
        return []
    return [
        {
            **item,
            "label": EVENT_LABELS.get(str(item.get("kind")), str(item.get("kind") or "event")),
        }
        for item in list_recent_worklog(root, limit=limit)
    ]


def build_mission_control_snapshot(
    root: Path,
    *,
    history_enabled: bool,
    codex_runner_ready: bool,
    private_only: bool,
    captain_configured: bool,
    tmux_runner_enabled: bool,
    codex_runner_enabled: bool,
) -> dict[str, Any]:
    plan = select_active_plan(root, history_enabled=history_enabled)
    agents = list_all_agents(root, codex_runner_ready=codex_runner_ready, private_only=private_only)
    agents_by_id = {str(agent.get("id") or ""): agent for agent in agents}
    step_rows = build_plan_step_rows(plan, root, agents_by_id=agents_by_id) if plan else []
    mission = build_mission_header(plan, step_rows)
    worklog_items = _worklog_items_with_labels(root, history_enabled=history_enabled)
    agent_items = build_agents_health_items(
        root,
        codex_runner_ready=codex_runner_ready,
        private_only=private_only,
        plan=plan,
        captain_configured=captain_configured,
    )
    safety = build_safety_payload(
        codex_runner_ready=codex_runner_ready,
        tmux_runner_enabled=tmux_runner_enabled,
        codex_runner_enabled=codex_runner_enabled,
        jules_runnable=False,
    )
    return {
        "service": "mcharness-control-plane",
        "generated_at": _now_iso(),
        "mission": mission,
        "plan": {
            "plan_id": plan.get("plan_id") if plan else None,
            "steps": step_rows,
        },
        "timeline": {"items": worklog_items},
        "worklog": {"items": worklog_items[:30]},
        "proof_gates": build_proof_gates_payload(root, history_enabled=history_enabled),
        "agents": {
            "summary": build_agents_summary(agent_items),
            "items": agent_items,
        },
        "safety": safety,
        "next_move": build_next_move(
            mission,
            step_rows,
            codex_runner_ready=codex_runner_ready,
            captain_configured=captain_configured,
        ),
    }


def pause_mission(root: Path, mission_id: str, *, note: str | None = None) -> dict[str, Any]:
    return pause_mission_plan(root, mission_id, note=note)


def adjust_mission_plan(
    root: Path,
    mission_id: str,
    *,
    note: str | None = None,
    adjustments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return request_plan_adjustment(root, mission_id, note=note, adjustments=adjustments)