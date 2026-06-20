"""Mission worklog aggregation from real Captain, run, and evidence activity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .captain_plans import plans_index_path
from .runner_sessions import runner_events_path
from .proof_gates import gates_index_path
from .run_history import (
    _prompt_excerpt,
    _read_json_list,
    evidence_index_path,
    redact_secrets,
    runs_index_path,
)

EVENT_LABELS: dict[str, str] = {
    "plan_created": "Plan created",
    "step_dispatched": "Step dispatched",
    "run_created": "Run started",
    "evidence_saved": "Evidence saved",
    "step_completed": "Step completed",
    "step_revised": "Step revised",
    "plan_stopped": "Plan stopped",
    "mission_paused": "Mission paused",
    "plan_adjustment_requested": "Plan adjustment requested",
    "gate_created": "Proof gate created",
    "gate_approved": "Proof gate approved",
    "gate_blocked": "Proof gate blocked",
    "gate_needs_more_evidence": "More evidence requested",
    "runner_sessions_cleaned": "Runner sessions cleaned",
}

GATE_DECISION_KINDS: dict[str, tuple[str, str]] = {
    "approve": ("gate_approved", "approved"),
    "block": ("gate_blocked", "blocked"),
    "request_more_evidence": ("gate_needs_more_evidence", "needs_more_evidence"),
}

DECISION_ACTIONS: dict[str, tuple[str, str]] = {
    "plan_created": ("plan_created", "saved"),
    "step_dispatched": ("step_dispatched", "running"),
    "step_completed": ("step_completed", "completed"),
    "step_revised": ("step_revised", "saved"),
    "plan_stopped": ("plan_stopped", "stopped"),
    "mission_paused": ("mission_paused", "stopped"),
    "plan_adjustment_requested": ("plan_adjustment_requested", "saved"),
}

RUN_STATUS_MAP: dict[str, str] = {
    "dispatched": "running",
    "running": "running",
    "completed": "completed",
    "failed": "stopped",
    "cancelled": "stopped",
}


def _read_plans(root: Path) -> list[dict[str, Any]]:
    path = plans_index_path(root)
    if not path.exists():
        return []
    return _read_json_list(path)


def _sanitize_worklog_item(item: dict[str, Any]) -> dict[str, Any]:
    title, _ = redact_secrets(str(item.get("title") or ""))
    summary, _ = redact_secrets(str(item.get("summary") or ""))
    return {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "title": title,
        "summary": summary,
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "links": dict(item.get("links") or {}),
    }


def list_recent_worklog(root: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for plan in _read_plans(root):
        plan_id = str(plan.get("plan_id") or "")
        plan_title = str(plan.get("title") or plan.get("goal") or "Captain plan")
        steps_by_id = {str(step.get("step_id")): step for step in plan.get("steps") or []}
        for entry in plan.get("decision_log") or []:
            action = str(entry.get("action") or "")
            mapped = DECISION_ACTIONS.get(action)
            if not mapped:
                continue
            kind, status = mapped
            step_id = entry.get("step_id")
            step = steps_by_id.get(str(step_id)) if step_id else None
            links: dict[str, str] = {}
            if plan_id:
                links["plan_id"] = plan_id
            if step_id:
                links["step_id"] = str(step_id)
            if step and step.get("run_id"):
                links["run_id"] = str(step["run_id"])
            detail = str(entry.get("detail") or "")
            title = plan_title
            if step and step.get("title"):
                title = f"{plan_title} · {step['title']}"
            created_at = entry.get("at")
            items.append(
                {
                    "id": f"wl_{plan_id}_{created_at}_{action}",
                    "kind": kind,
                    "title": title,
                    "summary": detail,
                    "status": status,
                    "created_at": created_at,
                    "links": links,
                }
            )

    for run in _read_json_list(runs_index_path(root)):
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        prompt = _prompt_excerpt(str(run.get("prompt") or ""), 220)
        links: dict[str, str] = {"run_id": run_id}
        if run.get("plan_id"):
            links["plan_id"] = str(run["plan_id"])
        items.append(
            {
                "id": f"wl_run_{run_id}",
                "kind": "run_created",
                "title": str(run.get("title") or run_id),
                "summary": prompt or f"Agent run {run_id}",
                "status": RUN_STATUS_MAP.get(str(run.get("status") or ""), "saved"),
                "created_at": run.get("started_at"),
                "links": links,
            }
        )

    for gate in _read_json_list(gates_index_path(root)):
        gate_id = str(gate.get("gate_id") or "")
        if not gate_id:
            continue
        links: dict[str, str] = {"gate_id": gate_id}
        if gate.get("run_id"):
            links["run_id"] = str(gate["run_id"])
        if gate.get("plan_id"):
            links["plan_id"] = str(gate["plan_id"])
        if gate.get("step_id"):
            links["step_id"] = str(gate["step_id"])
        for evidence_id in gate.get("evidence_ids") or []:
            if evidence_id:
                links.setdefault("evidence_id", str(evidence_id))
                break
        items.append(
            {
                "id": f"wl_gate_created_{gate_id}",
                "kind": "gate_created",
                "title": str(gate.get("title") or gate_id),
                "summary": str(gate.get("summary") or "Manual proof gate created."),
                "status": "pending",
                "created_at": gate.get("created_at"),
                "links": links,
            }
        )
        for entry in gate.get("decision_log") or []:
            decision = str(entry.get("decision") or "")
            mapped = GATE_DECISION_KINDS.get(decision)
            if not mapped:
                continue
            kind, status = mapped
            items.append(
                {
                    "id": f"wl_{kind}_{gate_id}_{entry.get('at')}",
                    "kind": kind,
                    "title": str(gate.get("title") or gate_id),
                    "summary": str(entry.get("reason") or f"Gate {decision.replace('_', ' ')}."),
                    "status": status,
                    "created_at": entry.get("at") or gate.get("decided_at"),
                    "links": links,
                }
            )

    for evidence in _read_json_list(evidence_index_path(root)):
        evidence_id = str(evidence.get("evidence_id") or "")
        if not evidence_id:
            continue
        links: dict[str, str] = {"evidence_id": evidence_id}
        if evidence.get("run_id"):
            links["run_id"] = str(evidence["run_id"])
        items.append(
            {
                "id": f"wl_evidence_{evidence_id}",
                "kind": "evidence_saved",
                "title": str(evidence.get("title") or evidence_id),
                "summary": str(evidence.get("summary") or evidence.get("content_excerpt") or "Evidence saved."),
                "status": "saved",
                "created_at": evidence.get("created_at"),
                "links": links,
            }
        )

    for event in _read_json_list(runner_events_path(root)):
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        items.append(
            {
                "id": event_id,
                "kind": str(event.get("kind") or "runner_sessions_cleaned"),
                "title": str(event.get("title") or "Runner sessions cleaned"),
                "summary": str(event.get("summary") or ""),
                "status": str(event.get("status") or "stopped"),
                "created_at": event.get("created_at"),
                "links": dict(event.get("links") or {}),
            }
        )

    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(_sanitize_worklog_item(item))
    return deduped[:limit]