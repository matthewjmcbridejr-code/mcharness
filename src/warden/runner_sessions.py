"""Safe inventory and cleanup for Warden-managed tmux runner sessions."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from .run_history import list_recent_runs, redact_secrets

_FILE_LOCK = threading.Lock()

RUNNER_SESSION_PREFIX = "mch_run_"
BLOCKED_SESSION_NAMES = frozenset({"0", "1", "2", "3", "main", "dev", "grok"})
DEFAULT_MAX_ACTIVE_RUNNER_SESSIONS = 4
DEFAULT_STALE_AFTER_SECONDS = 7200

ACTIVE_RUN_STATUSES = frozenset({"running", "dispatched", "waiting_for_codex", "prompt_sent", "awaiting_response", "starting"})
ACTIVE_RUNNER_STATE_STATUSES = frozenset({"running", "waiting_for_codex", "prompt_sent", "awaiting_response", "starting"})

SafeCmd = Callable[..., Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def max_active_runner_sessions() -> int:
    raw = (os.environ.get("MCHARNESS_MAX_ACTIVE_RUNNER_SESSIONS") or "").strip()
    if not raw:
        return DEFAULT_MAX_ACTIVE_RUNNER_SESSIONS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_ACTIVE_RUNNER_SESSIONS
    return max(1, min(value, 32))


def is_manageable_runner_session(session_name: str) -> bool:
    name = str(session_name or "").strip()
    if not name.startswith(RUNNER_SESSION_PREFIX):
        return False
    if name in BLOCKED_SESSION_NAMES:
        return False
    suffix = name[len(RUNNER_SESSION_PREFIX) :]
    if not suffix or not re.fullmatch(r"[A-Za-z0-9_]+", suffix):
        return False
    return True


def linked_run_id_from_session_name(session_name: str) -> str | None:
    if not is_manageable_runner_session(session_name):
        return None
    candidate = session_name[len(RUNNER_SESSION_PREFIX) :]
    if candidate.startswith("run_"):
        return candidate
    return None


def sanitize_command_name(command: str | None) -> str:
    text = str(command or "").strip()
    if not text:
        return ""
    token = text.split()[0] if text.split() else text
    token = token.split("/")[-1]
    safe, _ = redact_secrets(token)
    return safe[:80]


def _parse_tmux_timestamp(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if "." in text:
            return int(float(text))
        return int(text)
    except ValueError:
        return None


def parse_tmux_list_sessions_output(stdout: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in (stdout or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rows.append(
            {
                "session_name": parts[0].strip(),
                "session_created": parts[1].strip(),
                "session_activity": parts[2].strip(),
                "session_attached": parts[3].strip(),
            }
        )
    return rows


def parse_tmux_list_panes_output(stdout: str) -> dict[str, str]:
    line = (stdout or "").splitlines()[0] if (stdout or "").splitlines() else ""
    if not line:
        return {}
    parts = line.split("\t")
    if len(parts) < 3:
        return {}
    return {
        "pane_pid": parts[0].strip(),
        "pane_current_command": parts[1].strip(),
        "pane_title": parts[2].strip(),
    }


def _active_run_ids(root: Path, runner_state_root: Path) -> set[str]:
    active: set[str] = set()
    for run in list_recent_runs(root, limit=100):
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        if str(run.get("status") or "") in ACTIVE_RUN_STATUSES:
            active.add(run_id)
    if runner_state_root.exists():
        for path in runner_state_root.glob("*.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(state.get("status") or "") not in ACTIVE_RUNNER_STATE_STATUSES:
                continue
            runner_id = str(state.get("runner_id") or "")
            if runner_id:
                active.add(runner_id)
            tmux_name = str(state.get("tmux_session_name") or "")
            linked = linked_run_id_from_session_name(tmux_name)
            if linked:
                active.add(linked)
    return active


def _session_age_seconds(created_ts: int | None, now_ts: int) -> int | None:
    if created_ts is None:
        return None
    age = now_ts - created_ts
    return max(0, age)


def build_runner_session_item(
    session_row: dict[str, str],
    pane_row: dict[str, str],
    *,
    now_ts: int,
    active_run_ids: set[str],
    include_details: bool,
) -> dict[str, Any] | None:
    session_name = session_row.get("session_name") or ""
    if not is_manageable_runner_session(session_name):
        return None
    created_ts = _parse_tmux_timestamp(session_row.get("session_created"))
    age_seconds = _session_age_seconds(created_ts, now_ts)
    linked_run_id = linked_run_id_from_session_name(session_name)
    pane_pid_raw = pane_row.get("pane_pid")
    pane_pid = None
    if include_details and pane_pid_raw and str(pane_pid_raw).isdigit():
        pane_pid = int(pane_pid_raw)
    command = sanitize_command_name(pane_row.get("pane_current_command"))
    title = str(pane_row.get("pane_title") or "").strip()
    title, _ = redact_secrets(title[:120])
    attached = str(session_row.get("session_attached") or "0") == "1"
    dead = command.lower() in {"[dead]", "dead"} or str(pane_pid_raw or "").lower() == "dead"
    active = bool(linked_run_id and linked_run_id in active_run_ids)
    item: dict[str, Any] = {
        "session_name": session_name,
        "safe_to_manage": True,
        "created_at": datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat() if created_ts else None,
        "age_seconds": age_seconds,
        "active": active,
        "dead": dead,
        "stale": False,
        "linked_run_id": linked_run_id,
    }
    if include_details:
        item["pane_pid"] = pane_pid
        item["command"] = command or None
        item["title"] = title or None
        item["attached"] = attached
    return item


def list_runner_sessions(
    *,
    safe_cmd: SafeCmd,
    runner_state_root: Path,
    root: Path,
    include_details: bool = True,
) -> list[dict[str, Any]]:
    list_res = safe_cmd(
        ["tmux", "list-sessions", "-F", "#{session_name}\t#{session_created}\t#{session_activity}\t#{session_attached}"],
        timeout=3.0,
    )
    if list_res is None or list_res.returncode != 0:
        return []
    session_rows = parse_tmux_list_sessions_output(list_res.stdout or "")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    active_run_ids = _active_run_ids(root, runner_state_root)
    items: list[dict[str, Any]] = []
    for row in session_rows:
        name = row.get("session_name") or ""
        if not is_manageable_runner_session(name):
            continue
        pane_res = safe_cmd(
            ["tmux", "list-panes", "-t", name, "-F", "#{pane_pid}\t#{pane_current_command}\t#{pane_title}"],
            timeout=2.0,
        )
        pane_row = parse_tmux_list_panes_output(pane_res.stdout if pane_res and pane_res.returncode == 0 else "")
        built = build_runner_session_item(
            row,
            pane_row,
            now_ts=now_ts,
            active_run_ids=active_run_ids,
            include_details=include_details,
        )
        if built is not None:
            items.append(built)
    items.sort(key=lambda item: str(item.get("session_name") or ""))
    return items


def classify_runner_sessions(
    items: list[dict[str, Any]],
    *,
    stale_after_seconds: int,
) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        age = row.get("age_seconds")
        active = bool(row.get("active"))
        dead = bool(row.get("dead"))
        stale = False
        if not dead and isinstance(age, int) and age >= stale_after_seconds and not active:
            stale = True
        row["stale"] = stale
        classified.append(row)
    return classified


def build_runner_session_inventory(
    root: Path,
    *,
    safe_cmd: SafeCmd,
    runner_state_root: Path,
    include_details: bool = True,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    raw_items = list_runner_sessions(
        safe_cmd=safe_cmd,
        runner_state_root=runner_state_root,
        root=root,
        include_details=include_details,
    )
    items = classify_runner_sessions(raw_items, stale_after_seconds=stale_after_seconds)
    live_items = [item for item in items if not item.get("dead")]
    active_count = sum(1 for item in live_items if item.get("active"))
    stale_count = sum(1 for item in items if item.get("stale"))
    return {
        "generated_at": _now_iso(),
        "max_active_runner_sessions": max_active_runner_sessions(),
        "total_runner_sessions": len(items),
        "active_runner_sessions": len(live_items),
        "stale_runner_sessions": stale_count,
        "items": items,
    }


def runner_sessions_safety_summary(inventory: dict[str, Any]) -> dict[str, Any]:
    active = int(inventory.get("active_runner_sessions") or 0)
    maximum = int(inventory.get("max_active_runner_sessions") or DEFAULT_MAX_ACTIVE_RUNNER_SESSIONS)
    stale = int(inventory.get("stale_runner_sessions") or 0)
    if active >= maximum:
        return {
            "key": "runner_sessions",
            "label": "Runner sessions",
            "status": "limit_reached",
            "severity": "danger",
            "summary": "Runner session limit reached. Clean stale sessions first.",
        }
    if stale > 0 or active >= max(1, maximum - 1):
        return {
            "key": "runner_sessions",
            "label": "Runner sessions",
            "status": "warning",
            "severity": "warning",
            "summary": f"{active} active runner sessions ({stale} stale).",
        }
    return {
        "key": "runner_sessions",
        "label": "Runner sessions",
        "status": "healthy",
        "severity": "good",
        "summary": f"{active} active runner session{'s' if active != 1 else ''}.",
    }


def runner_events_path(root: Path) -> Path:
    return root / "runner" / "events.json"


def append_runner_cleanup_event(root: Path, *, killed: list[str], skipped: list[str]) -> None:
    if not killed:
        return
    path = runner_events_path(root)
    with _FILE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    rows = data
            except Exception:
                rows = []
        rows.insert(
            0,
            {
                "id": f"runner_cleanup_{_now_iso()}",
                "kind": "runner_sessions_cleaned",
                "title": "Runner sessions cleaned",
                "summary": f"Removed {len(killed)} stale runner session(s).",
                "status": "stopped",
                "created_at": _now_iso(),
                "links": {"session_names": killed[:20]},
                "skipped_count": len(skipped),
            },
        )
        path.write_text(json.dumps(rows[:100], indent=2), encoding="utf-8")


def cleanup_runner_sessions(
    root: Path,
    *,
    safe_cmd: SafeCmd,
    runner_state_root: Path,
    confirm: bool = False,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    inventory = build_runner_session_inventory(
        root,
        safe_cmd=safe_cmd,
        runner_state_root=runner_state_root,
        include_details=True,
        stale_after_seconds=stale_after_seconds,
    )
    candidates: list[str] = []
    skipped: list[dict[str, str]] = []
    killed: list[str] = []
    errors: list[dict[str, str]] = []

    for item in inventory.get("items") or []:
        name = str(item.get("session_name") or "")
        if not is_manageable_runner_session(name):
            skipped.append({"session_name": name, "reason": "not_manageable"})
            continue
        if item.get("active"):
            skipped.append({"session_name": name, "reason": "linked_active_run"})
            continue
        if not item.get("stale"):
            skipped.append({"session_name": name, "reason": "not_stale"})
            continue
        if item.get("dead"):
            skipped.append({"session_name": name, "reason": "already_dead"})
            continue
        candidates.append(name)

    if not confirm:
        return {
            "dry_run": True,
            "candidates": candidates,
            "killed": [],
            "skipped": skipped,
            "errors": [],
            "inventory": {
                "total_runner_sessions": inventory.get("total_runner_sessions"),
                "active_runner_sessions": inventory.get("active_runner_sessions"),
                "stale_runner_sessions": inventory.get("stale_runner_sessions"),
            },
        }

    for name in candidates:
        if not is_manageable_runner_session(name):
            skipped.append({"session_name": name, "reason": "not_manageable"})
            continue
        res = safe_cmd(["tmux", "kill-session", "-t", name], timeout=2.0)
        if res is not None and res.returncode == 0:
            killed.append(name)
        else:
            errors.append({"session_name": name, "reason": "kill_failed"})

    append_runner_cleanup_event(root, killed=killed, skipped=[row["session_name"] for row in skipped])
    return {
        "dry_run": False,
        "candidates": candidates,
        "killed": killed,
        "skipped": skipped,
        "errors": errors,
        "inventory": {
            "total_runner_sessions": inventory.get("total_runner_sessions"),
            "active_runner_sessions": inventory.get("active_runner_sessions"),
            "stale_runner_sessions": inventory.get("stale_runner_sessions"),
        },
    }


def assert_runner_session_capacity(
    root: Path,
    *,
    safe_cmd: SafeCmd,
    runner_state_root: Path,
) -> None:
    inventory = build_runner_session_inventory(
        root,
        safe_cmd=safe_cmd,
        runner_state_root=runner_state_root,
        include_details=False,
    )
    active = int(inventory.get("active_runner_sessions") or 0)
    maximum = int(inventory.get("max_active_runner_sessions") or DEFAULT_MAX_ACTIVE_RUNNER_SESSIONS)
    if active >= maximum:
        raise HTTPException(
            status_code=409,
            detail="Runner session limit reached. Clean stale sessions first.",
        )