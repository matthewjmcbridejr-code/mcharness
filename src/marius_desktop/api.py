import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .captain import (
    router as captain_router,
    CaptainAssignmentCompleteRequest,
    CaptainAssignmentEvidenceRequest,
    CaptainPlanRequest,
    CaptainQueueItemCreateRequest,
    add_captain_queue_item,
    assign_captain_minions,
    complete_captain_assignment,
    continue_captain_run,
    create_captain_state_machine_run,
    export_captain_queue_item,
    plan_captain_run,
    queue_captain_run,
    record_captain_assignment_evidence,
)
from .contracts import CapabilityStatus, TaskState, WorkerRun
from .graph import (
    CHECKPOINT_DB_PATH,
    LANGGRAPH_AVAILABLE,
    McTableTaskGraph,
    TASKS_DIR,
    checkpoint_file_exists,
    get_runtime_capabilities,
)
from .workbench import (
    router as workbench_router,
    STORE as WORKBENCH_STORE,
    WorkbenchArtifactCreateRequest,
    WorkbenchEvidenceRecordCreateRequest,
    WorkbenchRunEventCreateRequest,
    WorkbenchRunProofGateDecisionRequest,
    WorkbenchThreadCreateRequest,
    WorkbenchThreadUpdateRequest,
)
from .worker import WorkerStub, ALLOWED_COMMANDS

router = APIRouter(prefix="/api/marius", tags=["marius-desktop"])
router.include_router(captain_router)
router.include_router(workbench_router)

mcharness_router = APIRouter(prefix="/api/mcharness", tags=["mcharness"])
legacy_router = APIRouter(tags=["marius-desktop-legacy"])

SAFE_REPO_PATHS = [
    Path("/root/hybrid-agent-os"),
    Path("/root/mcharness-public-export"),
]
MCTABLE_ROOT = Path(os.getenv("MCHARNESS_DATA_ROOT", "_mctable"))
ARTIFACT_BODY_ROOT = MCTABLE_ROOT / "mcharness" / "artifacts"
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_LANES = [
    {
        "lane_id": "codex_cli",
        "title": "Codex CLI",
        "implemented": True,
        "manual_only": True,
    },
    {
        "lane_id": "agy_cli",
        "title": "AGY / Antigravity CLI",
        "implemented": True,
        "manual_only": True,
    },
    {
        "lane_id": "manual_paste",
        "title": "Manual paste-back",
        "implemented": True,
        "manual_only": True,
    },
    {
        "lane_id": "grok_placeholder",
        "title": "Grok",
        "implemented": False,
        "manual_only": True,
    },
    {
        "lane_id": "jules_placeholder",
        "title": "Jules",
        "implemented": False,
        "manual_only": True,
    },
    {
        "lane_id": "opencode_placeholder",
        "title": "OpenCode",
        "implemented": False,
        "manual_only": True,
    },
    {
        "lane_id": "fake_test_lane",
        "title": "Fake Test Lane (internal/harmless for automated proof only)",
        "implemented": True,
        "manual_only": False,
        "test_only": True,
    },
]


def _env_flag(*names: str, default: str = "false") -> bool:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value.strip().lower() in {"1", "true", "yes", "on"}
    return default.strip().lower() in {"1", "true", "yes", "on"}


def _git_commit() -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    commit = proc.stdout.strip()
    return commit or None


def _public_write_enabled() -> bool:
    return _env_flag("MCHARNESS_PUBLIC_WRITE_ENABLED", "MCHARNESSS_PUBLIC_WRITE_ENABLED", default="true")


def _tmux_runner_enabled() -> bool:
    # Tolerate the common misspelling variant as done for PUBLIC_WRITE
    return _env_flag(
        "MCHARNESS_TMUX_RUNNER_ENABLED",
        "MCHARNESSS_TMUX_RUNNER_ENABLED",
        default="false",
    )


def _codex_runner_enabled() -> bool:
    # Explicit second gate for real Codex (personal manual smoke only). Tolerate misspelling.
    return _env_flag(
        "MCHARNESS_CODEX_RUNNER_ENABLED",
        "MCHARNESSS_CODEX_RUNNER_ENABLED",
        default="false",
    )


def _safe_cmd(cmd: list[str], timeout: float = 2.5, cwd: str | None = None) -> subprocess.CompletedProcess | None:
    """Run a command with timeout; never raise, always return structured result or None."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except Exception:
        return None


def _detect_executable(name: str) -> dict[str, Any]:
    """Safe, non-interactive detection using command -v + optional --version. No auth files, no login, no secrets."""
    exe: Optional[str] = None
    version: Optional[str] = None
    # Per spec: use command -v
    res = _safe_cmd(["bash", "-c", f"command -v {name} || true"], timeout=2.0)
    if res is not None and res.returncode == 0 and res.stdout.strip():
        exe = res.stdout.strip().splitlines()[0].strip() or None
    if exe:
        # Try --version (or -v for some); tolerate non-zero (some CLIs print version to stderr)
        for args in ([exe, "--version"], [exe, "-v"], [exe, "--help"]):
            vres = _safe_cmd(args, timeout=3.0)
            if vres is not None and (vres.stdout or vres.stderr):
                version = (vres.stdout or vres.stderr).strip().splitlines()[0][:140]
                break
    return {
        "installed": bool(exe),
        "executable_path": exe,
        "version": version,
    }


def _get_git_status(path: Path) -> dict[str, Any]:
    """Safe git status for allowlisted repo only. Timeouts, no arbitrary paths."""
    if not path.exists() or not (path / ".git").exists():
        return {
            "current_branch": None,
            "dirty": False,
            "changed_files_count": 0,
            "last_commit_short": None,
            "status_summary": "unavailable (no .git)",
            "safety_notes": ["git metadata unavailable"],
        }
    info: dict[str, Any] = {}
    for cmd, key in (
        (["git", "rev-parse", "--abbrev-ref", "HEAD"], "current_branch"),
        (["git", "rev-parse", "--short", "HEAD"], "last_commit_short"),
    ):
        r = _safe_cmd(cmd, timeout=2.0, cwd=str(path))
        info[key] = r.stdout.strip() if (r is not None and r.returncode == 0) else None
    r = _safe_cmd(["git", "status", "--porcelain"], timeout=3.0, cwd=str(path))
    if r is not None and r.returncode == 0:
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        info["changed_files_count"] = len(lines)
        info["dirty"] = len(lines) > 0
    else:
        info["changed_files_count"] = 0
        info["dirty"] = False
    branch = info.get("current_branch") or ""
    summary = f"{'dirty' if info.get('dirty') else 'clean'} ({info.get('changed_files_count', 0)} changed)"
    if branch:
        summary += f" on {branch}"
    info["status_summary"] = summary
    info["safety_notes"] = []
    return info


def _require_public_write_access(request: Request) -> None:
    if _public_write_enabled():
        return
    expected_token = os.getenv("MCHARNESS_ADMIN_TOKEN", "").strip()
    presented_token = request.headers.get("X-MCHarness-Admin-Token", "").strip()
    if expected_token and presented_token == expected_token:
        return
    raise HTTPException(
        status_code=403,
        detail="Public write access is disabled for this deployment.",
    )

class TaskCreateRequest(BaseModel):
    task_id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    title: str
    description: str
    command: str
    args: List[str] = Field(default_factory=list)

class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "edit_state"]
    actor: str
    reviewer_note: Optional[str] = None
    state_patch: Dict[str, Any] = Field(default_factory=dict)


class McHarnessSessionCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    plan_instruction: str = Field(min_length=1)
    repo_path: str = Field(min_length=1)
    agent_lane: str = Field(min_length=1)


class McHarnessQueueRequest(BaseModel):
    title: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    target_role: Literal["ui_inspector", "safety_auditor", "test_runner", "implementer", "docs_writer", "reviewer"] = "reviewer"
    file_scope: list[str] = Field(default_factory=list)
    forbidden_file_scope: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)


class McHarnessPromptExportRequest(BaseModel):
    queue_item_id: str = Field(min_length=1)
    mark_sent: bool = False


class McHarnessManualResultRequest(BaseModel):
    assignment_id: Optional[str] = None
    summary: str = Field(min_length=1)
    transcript: Optional[str] = None
    source_ref: Optional[str] = None
    verdict: Literal["passed", "unknown", "blocked", "failed"] = "passed"
    complete_assignment: bool = False
    git_status: Optional[str] = None
    git_diff_summary: Optional[str] = None
    test_output: Optional[str] = None


class McHarnessGateDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected", "edit_requested"]
    note: Optional[str] = None
    continue_after: bool = False


class McHarnessRunnerIntentRequest(BaseModel):
    lane_id: str = Field(min_length=1)
    repo_id: str = Field(min_length=1)
    queue_item_id: Optional[str] = None
    prompt_artifact_id: Optional[str] = None
    mode: str = "dry_run"


class McHarnessRunnerStartRequest(BaseModel):
    lane_id: str = Field(min_length=1)
    repo_id: str = Field(min_length=1)
    queue_item_id: Optional[str] = None
    prompt_artifact_id: Optional[str] = None


def _repo_entries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in SAFE_REPO_PATHS:
        base = {
            "repo_id": path.name,
            "label": path.name,
            "path": str(path),
            "exists": path.exists(),
            "git_dir_present": (path / ".git").exists(),
        }
        if path.exists() and (path / ".git").exists():
            git_info = _get_git_status(path)
        else:
            git_info = {
                "current_branch": None,
                "dirty": False,
                "changed_files_count": 0,
                "last_commit_short": None,
                "status_summary": "unavailable",
                "safety_notes": ["path does not exist or is not a git repo"] if not path.exists() else [],
            }
        base.update(git_info)
        rows.append(base)
    return rows


def _lane_entries() -> list[dict[str, Any]]:
    """Return rich lane objects (new fields) + legacy keys for compat. Safe checks only."""
    now = datetime.now(timezone.utc).isoformat()
    tmux_enabled = _tmux_runner_enabled()
    # base static for order + validation compat
    base_map = {entry["lane_id"]: entry for entry in AGENT_LANES}

    def _rich_for(lid: str, label: str, desc: str, is_manual: bool = False) -> dict[str, Any]:
        if is_manual:
            det = {"installed": True, "executable_path": None, "version": None}
            auth = "not_checked"
            rmode = "manual"
            notes = ["Manual paste-back flow. Operator performs all CLI steps locally. No server-side execution."]
        elif lid == "fake_test_lane":
            det = {"installed": True, "executable_path": None, "version": "internal-fake-1.0"}
            auth = "not_checked"
            rmode = "controlled_run_ready"
            notes = [
                "FAKE TEST LANE: harmless python -c print only. No provider calls, no usage burn, no real CLI.",
                "For automated tests and proof only. Gated behind MCHARNESS_TMUX_RUNNER_ENABLED or test override.",
            ]
        else:
            det = _detect_executable(lid.split("_")[0])  # codex or agy
            auth = "unknown" if det["installed"] else "not_detected"
            rmode = "dry_run_ready" if det["installed"] else "controlled_run_disabled"
            notes = []
            if lid == "codex_cli":
                # Improve auth for codex using safe non-int doctor (no secrets, no login)
                if det["installed"]:
                    exe = det["executable_path"]
                    dres = _safe_cmd([exe, "doctor"], timeout=5.0)
                    dout = ((dres.stdout or "") + (dres.stderr or "")).lower() if dres else ""
                    if dres is not None and (dres.returncode == 0) and any(k in dout for k in ["authenticated", "logged in", "ready", "health"]):
                        auth = "likely_ready"
                    else:
                        auth = "unknown"
                    tmux_f = _tmux_runner_enabled()
                    codex_f = _codex_runner_enabled()
                    rmode = "controlled_run_ready" if (det["installed"] and tmux_f and codex_f) else "controlled_run_disabled"
                    notes.append("Real Codex gated: requires BOTH MCHARNESS_TMUX_RUNNER_ENABLED=true AND MCHARNESS_CODEX_RUNNER_ENABLED=true for controlled start.")
                    notes.append("Uses codex exec (non-int) + --cd + --output-last-message for transcript. Attach mode fallback via tmux if needed.")
                    notes.append("Auth via safe non-interactive 'codex doctor' check only; no token files or login commands ever inspected.")
                else:
                    notes.append("Codex not found via command -v. Install via subscription to enable (preview still works).")
            elif det["installed"]:
                notes.append("Real execution disabled (public_manual + MCHARNESS_TMUX_RUNNER_ENABLED=false).")
                notes.append("Dry-run intent preview supported. No auth files, cookies, or secrets are inspected.")
            else:
                notes.append("Executable not found via command -v. Install via your subscription to enable (preview still works).")
        legacy = base_map.get(lid, {"implemented": False, "manual_only": True})
        return {
            "id": lid,
            "label": label,
            "description": desc,
            "installed": det["installed"],
            "executable_path": det["executable_path"],
            "version": det["version"],
            "auth_status": auth,
            "runner_mode": rmode,
            "safety_notes": notes,
            "last_checked_at": now,
            # legacy for existing UI/tests
            "lane_id": lid,
            "title": label,
            "implemented": legacy.get("implemented", not is_manual),
            "manual_only": True,
        }

    rich = [
        _rich_for("codex_cli", "Codex CLI", "OpenAI Codex CLI for code generation/edits via subscription."),
        _rich_for("agy_cli", "AGY / Antigravity CLI", "AGY/Antigravity CLI coding agent (subscription)."),
        _rich_for("manual_paste", "Manual paste-back", "Copy prompt export and paste transcript/results back manually.", is_manual=True),
        _rich_for("grok_placeholder", "Grok", "Grok CLI (placeholder, not wired for preview)."),
        _rich_for("jules_placeholder", "Jules", "Jules (placeholder, not wired for preview)."),
        _rich_for("opencode_placeholder", "OpenCode", "OpenCode (placeholder, not wired for preview)."),
        _rich_for("fake_test_lane", "Fake Test Lane (internal/harmless for automated proof only)", "Internal fake lane for runner foundation tests/proof. Harmless python -c only."),
    ]
    # also surface tmux availability in notes for cli lanes if useful
    tmux_note = f"tmux available: {bool(_safe_cmd(['bash', '-c', 'command -v tmux || true'], timeout=1.0))}"
    for entry in rich:
        if entry["id"] in ("codex_cli", "agy_cli") and entry["installed"]:
            entry["safety_notes"].append(tmux_note)
    return rich


def _validate_repo_path(repo_path: str) -> Path:
    for entry in SAFE_REPO_PATHS:
        if str(entry) == repo_path:
            if not entry.exists():
                raise HTTPException(status_code=400, detail=f"Allowlisted repo path does not exist: {repo_path}")
            return entry
    raise HTTPException(status_code=400, detail=f"Repo path is not allowlisted: {repo_path}")


def _validate_agent_lane(agent_lane: str) -> dict[str, Any]:
    lane = next((entry for entry in AGENT_LANES if entry["lane_id"] == agent_lane), None)
    if lane is None:
        raise HTTPException(status_code=400, detail=f"Unknown agent lane: {agent_lane}")
    if not lane["implemented"]:
        raise HTTPException(status_code=400, detail=f"Agent lane is placeholder only: {agent_lane}")
    return lane


def _thread_for_session(session_id: str) -> dict[str, Any]:
    try:
        return WORKBENCH_STORE.get_thread(session_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}") from exc


def _run_for_session(session_id: str) -> dict[str, Any]:
    runs = WORKBENCH_STORE.list_runs_for_thread(session_id)
    if not runs:
        raise HTTPException(status_code=404, detail=f"No run found for session: {session_id}")
    return runs[0]


def _append_run_event(run_id: str, title: str, detail: str, severity: str = "info", event_type: str = "note") -> None:
    WORKBENCH_STORE.append_run_event(
        run_id,
        WorkbenchRunEventCreateRequest(
            event_type=event_type,
            title=title,
            detail=detail,
            severity=severity,  # type: ignore[arg-type]
        ),
    )


def _artifact_blob_path(thread_id: str, kind: str, extension: str) -> Path:
    suffix = extension.lstrip(".") or "txt"
    target_dir = ARTIFACT_BODY_ROOT / thread_id
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{kind}-{uuid.uuid4().hex[:8]}.{suffix}"


def _create_artifact(thread_id: str, kind: str, title: str, body: str, summary: Optional[str] = None, extension: str = "txt") -> dict[str, Any]:
    path = _artifact_blob_path(thread_id, kind, extension)
    path.write_text(body, encoding="utf-8")
    artifact = WORKBENCH_STORE.create_artifact(
        WorkbenchArtifactCreateRequest(
            artifact_id=f"artifact_{uuid.uuid4().hex[:8]}",
            kind=kind,
            title=title,
            path=str(path),
            thread_id=thread_id,
            summary=summary or title,
            notes=None,
        )
    )
    return artifact.model_dump(mode="json")


def _create_run_summary_artifact(thread: dict[str, Any], run: dict[str, Any], note: str) -> dict[str, Any]:
    metadata = thread.get("metadata") or {}
    body = "\n".join(
        [
            "# McHarness Run Summary",
            f"- Session: {thread.get('title')}",
            f"- Session id: {thread.get('thread_id')}",
            f"- Repo/worktree: {metadata.get('repo_path', '(unknown)')}",
            f"- CLI lane: {metadata.get('agent_lane', '(unknown)')}",
            f"- Thread status: {thread.get('status')}",
            f"- Run id: {run.get('run_id')}",
            f"- Run status: {run.get('status')}",
            f"- Current step: {run.get('current_step')}",
            f"- Note: {note}",
        ]
    )
    return _create_artifact(thread["thread_id"], "run_summary", "Run summary", body, note, "md")


def _capture_git_status_artifacts(thread: dict[str, Any]) -> dict[str, Any]:
    metadata = thread.get("metadata") or {}
    repo_path = _validate_repo_path(metadata.get("repo_path", ""))
    status_proc = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--short"],
        capture_output=True,
        text=True,
        check=False,
    )
    diff_proc = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--stat"],
        capture_output=True,
        text=True,
        check=False,
    )
    status_text = status_proc.stdout.strip() or "(clean)"
    diff_text = diff_proc.stdout.strip() or "(no diff summary)"
    status_artifact = _create_artifact(
        thread["thread_id"],
        "git_status",
        "Git status",
        status_text + "\n",
        f"git status for {repo_path}",
        "txt",
    )
    diff_artifact = _create_artifact(
        thread["thread_id"],
        "git_diff_summary",
        "Git diff summary",
        diff_text + "\n",
        f"git diff summary for {repo_path}",
        "txt",
    )
    return {
        "repo_path": str(repo_path),
        "git_status": status_text,
        "git_diff_summary": diff_text,
        "artifacts": [status_artifact, diff_artifact],
    }


# --- Gated tmux runner foundation (fake_test_lane + controlled when enabled) ---

RUNNER_STATE_ROOT = MCTABLE_ROOT / "mcharness" / "runners"


def _runner_state_path(session_id: str) -> Path:
    RUNNER_STATE_ROOT.mkdir(parents=True, exist_ok=True)
    return RUNNER_STATE_ROOT / f"{session_id}.json"


def _load_runner_state(session_id: str) -> Optional[dict[str, Any]]:
    p = _runner_state_path(session_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_runner_state(state: dict[str, Any]) -> None:
    p = _runner_state_path(state["session_id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(p)


def _tmux_session_name(session_id: str, runner_id: str) -> str:
    # safe, short, alnum + _ only
    base = (session_id.replace("-", "") + runner_id.replace("-", ""))[-12:]
    return "mch_" + "".join(c if c.isalnum() else "_" for c in base)


def _get_tmux_transcript(name: str) -> str:
    """Prefer live pane capture for running sessions (so monitor shows actual Codex output).
    Fall back to previous file contents on exit.
    """
    if not name:
        return ""
    # Always try capture first if the session exists (live view)
    has = _safe_cmd(["tmux", "has-session", "-t", name], timeout=1.0)
    if has is not None and has.returncode == 0:
        res = _safe_cmd(["tmux", "capture-pane", "-p", "-t", name], timeout=3.0)
        if res is not None and res.returncode == 0:
            return res.stdout or ""
    # session gone or capture failed: use whatever is in the transcript file (final or previous captures)
    # (the file may have been appended to by send or prior captures)
    return ""


def _stop_tmux(name: str) -> None:
    _safe_cmd(["tmux", "kill-session", "-t", name], timeout=2.0)


def _start_fake_runner(state: dict[str, Any]) -> dict[str, Any]:
    """Harmless fake only. Uses pure long-running process in tmux so monitor can capture live + injected prompt text.
    No providers, no usage burn. For automated proof of interactive send/capture/stop.
    """
    name = state["tmux_session_name"]
    # Long-running harmless process (stays alive for send-keys and capture).
    # The typed prompt from send will appear in the tmux pane buffer (visible in capture).
    inner = "python -c \"import time,sys; print('FAKE_STARTED'); sys.stdout.flush(); time.sleep(300)\" "
    tmux_cmd = ["tmux", "new-session", "-d", "-s", name, "--", "bash", "-c", inner]
    res = _safe_cmd(tmux_cmd, timeout=5.0)
    if res is not None and res.returncode == 0:
        state["status"] = "running"
        state["notes"].append("tmux session started for fake_test_lane (long-running for live capture)")
    else:
        state["status"] = "failed"
        state["notes"].append(f"tmux start failed: {getattr(res, 'stderr', 'err') if res else 'subprocess err'}")
    return state


def _start_codex_runner(state: dict[str, Any], cwd: str) -> dict[str, Any]:
    """Launch Codex interactively in tmux (pure, no wrapper that forces exit).
    Keeps the tmux session + Codex TUI alive for live monitoring and later prompt injection.
    """
    name = state["tmux_session_name"]
    # Pure interactive launch in the allowlisted cwd. Codex will run its TUI and wait.
    # Use the binary name (resolvable in PATH for the service user).
    tmux_cmd = ["tmux", "new-session", "-d", "-s", name, "-c", cwd, "codex"]
    res = _safe_cmd(tmux_cmd, timeout=5.0)
    if res is not None and res.returncode == 0:
        state["status"] = "waiting_for_codex"
        state["notes"].append("codex interactive tmux session started; will inject prompt after ~10s delay")
        state["attach_command"] = f"tmux attach -t {name}"
    else:
        state["status"] = "failed"
        state["notes"].append(f"codex tmux start failed: {getattr(res, 'stderr', 'err') if res else 'subprocess err'}")
        state["attach_command"] = f"tmux attach -t {name}  # (may have failed to start)"
    return state


class McHarnessRunnerSendPrompt(BaseModel):
    prompt: str = Field(min_length=1)


class McHarnessRunnerSendKey(BaseModel):
    key: Literal["1", "2", "3", "Enter", "Esc", "Ctrl+C"]


ALLOWED_QUICK_REPLY_KEYS: dict[str, str] = {
    "1": "1",
    "2": "2",
    "3": "3",
    "Enter": "Enter",
    "Esc": "Escape",
    "Ctrl+C": "C-c",
}

ACTIVE_RUNNER_STATUSES = {"running", "waiting_for_codex", "prompt_sent"}


def _runner_transcript_excerpt(state: dict[str, Any], limit: int = 1200) -> str:
    text = ""
    transcript_path = state.get("transcript_file_path")
    if transcript_path:
        p = Path(transcript_path)
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                text = ""
    if not text:
        name = state.get("tmux_session_name", "")
        if name:
            text = _get_tmux_transcript(name)
    text = text or ""
    if len(text) > limit:
        return text[-limit:]
    return text


def _send_key_to_codex_runner(session_id: str, key: str) -> dict[str, Any]:
    state = _load_runner_state(session_id)
    if not state or state.get("lane_id") != "codex_cli":
        raise HTTPException(status_code=400, detail="Quick reply only supported for active codex_cli runner")
    if state.get("session_id") != session_id:
        raise HTTPException(status_code=400, detail="Runner state/session mismatch")

    status = state.get("status")
    if status not in ACTIVE_RUNNER_STATUSES:
        raise HTTPException(status_code=409, detail=f"Runner not active (status={status or 'unknown'})")

    name = state.get("tmux_session_name")
    if not name:
        raise HTTPException(status_code=400, detail="No tmux session for runner")
    expected_name = _tmux_session_name(session_id, str(state.get("runner_id", "")))
    if name != expected_name:
        raise HTTPException(status_code=400, detail="Runner tmux session mismatch")

    has = _safe_cmd(["tmux", "has-session", "-t", name], timeout=1.0)
    if has is None or has.returncode != 0:
        raise HTTPException(status_code=409, detail="No active tmux session for runner")

    tmux_key = ALLOWED_QUICK_REPLY_KEYS.get(key)
    if tmux_key is None:
        raise HTTPException(status_code=400, detail="Unsupported quick reply key")

    res = _safe_cmd(["tmux", "send-keys", "-t", name, tmux_key], timeout=2.5)
    if res is None or res.returncode != 0:
        raise HTTPException(status_code=502, detail="Failed to send quick reply to tmux runner")

    try:
        run = _run_for_session(session_id)
        _append_run_event(run.get("run_id", ""), "Quick reply sent", f"Sent quick reply key {key!r} to Codex via tmux", "info", "runner")
    except Exception:
        pass

    return {
        "ok": True,
        "session_id": session_id,
        "runner_id": state.get("runner_id"),
        "lane_id": state.get("lane_id"),
        "tmux_session_name": name,
        "sent_key": key,
        "status": state.get("status"),
        "transcript_excerpt": _runner_transcript_excerpt(state),
    }


def _send_prompt_to_codex_runner(session_id: str, prompt_text: str):
    """Safe, allowlisted only: send the (controlled) prompt text to the codex tmux runner via send-keys -l (literal).
    No arbitrary shell. Only called for codex lane after start + delay.
    """
    state = _load_runner_state(session_id)
    if not state or state.get("lane_id") != "codex_cli":
        raise HTTPException(status_code=400, detail="Send prompt only supported for active codex_cli runner")
    name = state.get("tmux_session_name")
    if not name:
        raise HTTPException(status_code=400, detail="No tmux session for runner")
    # Use -l for literal text (safe, no shell interp of user prompt)
    _safe_cmd(["tmux", "send-keys", "-t", name, "-l", prompt_text], timeout=5.0)
    _safe_cmd(["tmux", "send-keys", "-t", name, "Enter"], timeout=2.0)
    # append note to transcript file (for final evidence)
    try:
        p = Path(state["transcript_file_path"])
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n# [McHarness injected prompt @ {datetime.now(timezone.utc).isoformat()}]\n{prompt_text}\n")
    except Exception:
        pass
    state["status"] = "prompt_sent"
    state["notes"].append("prompt text injected via tmux send-keys -l + Enter; session kept alive for live monitoring")
    _save_runner_state(state)
    try:
        run = _run_for_session(session_id)
        _append_run_event(run.get("run_id", ""), "Prompt sent to Codex", "User task prompt injected via safe tmux send-keys", "info", "runner")
    except Exception:
        pass
    return {"ok": True}


@mcharness_router.post("/sessions/{session_id}/runner/send-prompt")
def post_mcharness_runner_send_prompt(session_id: str, payload: McHarnessRunnerSendPrompt):
    """Smallest safe endpoint to inject the modal prompt into the running codex tmux (after startup delay)."""
    _send_prompt_to_codex_runner(session_id, payload.prompt)
    return {"ok": True, "injected": True}


@mcharness_router.post("/sessions/{session_id}/runner/send-key")
def post_mcharness_runner_send_key(session_id: str, payload: McHarnessRunnerSendKey):
    return _send_key_to_codex_runner(session_id, payload.key)


@router.get("/capabilities", response_model=List[CapabilityStatus])
def get_capabilities():
    return get_runtime_capabilities()

@router.get("/status")
def get_status():
    return {
        "service": "marius-desktop-api",
        "status": "online",
        "langgraph_available": LANGGRAPH_AVAILABLE,
        "sqlite_checkpointing_available": LANGGRAPH_AVAILABLE,
        "checkpoint_db_path": str(CHECKPOINT_DB_PATH.resolve()),
        "checkpoint_exists": checkpoint_file_exists(),
        "mctable_root": str(MCTABLE_ROOT.resolve())
    }


@mcharness_router.get("/health")
def get_mcharness_health():
    repos = _repo_entries()
    lanes = _lane_entries()
    return {
        "ok": True,
        "service": "mcharness-control-plane",
        "commit": _git_commit(),
        "mode": "public_manual",
        "real_agent_launch_enabled": False,
        "arbitrary_command_execution_enabled": False,
        "public_write_enabled": _public_write_enabled(),
        "tmux_runner_enabled": _tmux_runner_enabled(),
        "codex_runner_enabled": _codex_runner_enabled(),
        "available_lanes_count": len(lanes),
        "repo_count": len(repos),
        "manual_mode": True,
    }

@router.get("/tasks", response_model=List[TaskState])
def get_tasks():
    tasks = []
    if TASKS_DIR.exists():
        graph = McTableTaskGraph()
        for p in TASKS_DIR.glob("*.json"):
            try:
                task_id = p.stem
                tasks.append(graph.load_state(task_id))
            except Exception:
                pass
    return tasks

@router.post("/tasks", response_model=TaskState, dependencies=[Depends(_require_public_write_access)])
def create_task(req: TaskCreateRequest):
    if req.command not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Command '{req.command}' is not allowlisted.")

    # Check if task already exists
    if (TASKS_DIR / f"{req.task_id}.json").exists():
        raise HTTPException(status_code=400, detail=f"Task {req.task_id} already exists.")

    graph = McTableTaskGraph()
    graph.create_task(req.task_id, req.title, req.description, req.command, req.args)
    return graph.drive_task_to_review(req.task_id)

@router.get("/tasks/{task_id}", response_model=TaskState)
def get_task(task_id: str):
    graph = McTableTaskGraph()
    try:
        return graph.load_state(task_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

@router.get("/tasks/{task_id}/events")
def get_task_events(task_id: str):
    graph = McTableTaskGraph()
    try:
        state = graph.load_state(task_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

    # Return a simple list of events based on the task state
    return [
        {"event": "task_created", "timestamp": state.created_at.isoformat()},
        {"event": "step_executed", "step": state.current_step, "timestamp": state.updated_at.isoformat()}
    ]

@router.post("/tasks/{task_id}/decision", response_model=TaskState, dependencies=[Depends(_require_public_write_access)])
def post_task_decision(task_id: str, req: DecisionRequest):
    graph = McTableTaskGraph()
    try:
        graph.load_state(task_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return graph.resume_task(
        task_id=task_id,
        decision=req.decision,
        actor=req.actor,
        reviewer_note=req.reviewer_note,
        state_patch=req.state_patch,
    )

@router.get("/worker-runs/{run_id}", response_model=WorkerRun)
def get_worker_run(run_id: str):
    try:
        return WorkerStub.get_status(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Worker run {run_id} not found.")

@router.get("/worker-runs/{run_id}/logs")
def get_worker_run_logs(run_id: str):
    try:
        logs_iterator = WorkerStub.stream_logs(run_id)
        return {"logs": "".join(list(logs_iterator))}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Worker run {run_id} not found.")

@router.post("/worker-runs/{run_id}/cancel", dependencies=[Depends(_require_public_write_access)])
def cancel_worker_run(run_id: str):
    try:
        WorkerStub.cancel_run(run_id)
        return {"status": "cancelled", "run_id": run_id}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Worker run {run_id} not found.")

@router.get("/agents")
def get_agents():
    return [
        {
            "agent_id": "fake-agent",
            "name": "Fake Agent stub",
            "capabilities": list(ALLOWED_COMMANDS)
        }
    ]


@mcharness_router.get("/repos")
def get_mcharness_repos():
    return {
        "service": "mcharness-control-plane",
        "mode": "server_control_plane",
        "repos": _repo_entries(),
    }


@mcharness_router.get("/agent-lanes")
def get_mcharness_agent_lanes():
    return {
        "service": "mcharness-control-plane",
        "manual_mode": True,
        "lanes": _lane_entries(),
    }


@mcharness_router.post("/sessions")
def create_mcharness_session(payload: McHarnessSessionCreateRequest):
    repo_path = _validate_repo_path(payload.repo_path)
    lane = _validate_agent_lane(payload.agent_lane)
    thread = WORKBENCH_STORE.create_thread(
        WorkbenchThreadCreateRequest(
            title=payload.title,
            goal=payload.objective,
            metadata={
                "repo_path": str(repo_path),
                "agent_lane": lane["lane_id"],
                "server_host_mode": True,
                "fake_or_manual_mode": True,
            },
        )
    )
    captain = create_captain_state_machine_run(thread["thread_id"], payload.objective).model_dump(mode="json")
    _append_run_event(captain["run_id"], "Session created", f"Server control plane created session for {repo_path}.", "info", "note")
    plan_captain_run(captain["captain_run_id"], CaptainPlanRequest(instruction=payload.plan_instruction))
    queue_captain_run(captain["captain_run_id"])
    assign_captain_minions(captain["captain_run_id"])
    thread = WORKBENCH_STORE.get_thread(thread["thread_id"])
    run = _run_for_session(thread["thread_id"])
    git_snapshot = _capture_git_status_artifacts(thread)
    run_summary = _create_run_summary_artifact(thread, run, "Session initialized in server control-plane mode.")
    return {
        "session_id": thread["thread_id"],
        "thread": thread,
        "run": run,
        "captain_run_id": captain["captain_run_id"],
        "repo_path": str(repo_path),
        "agent_lane": lane["lane_id"],
        "git_snapshot": git_snapshot,
        "run_summary_artifact": run_summary,
    }


@mcharness_router.post("/sessions/{session_id}/queue")
def queue_mcharness_prompt(session_id: str, payload: McHarnessQueueRequest):
    run = _run_for_session(session_id)
    state = add_captain_queue_item(
        run["run_id"],
        CaptainQueueItemCreateRequest(
            title=payload.title,
            prompt=payload.prompt,
            target_role=payload.target_role,
            file_scope=list(payload.file_scope),
            forbidden_file_scope=list(payload.forbidden_file_scope),
            evidence_required=list(payload.evidence_required),
            acceptance_checks=list(payload.acceptance_checks),
            export_format="generic_markdown",
        ),
    ).model_dump(mode="json")
    _append_run_event(run["run_id"], "Prompt queued", f"Queued prompt {payload.title}.", "info", "instruction")
    return {
        "session_id": session_id,
        "run_id": run["run_id"],
        "state": state,
    }


@mcharness_router.post("/sessions/{session_id}/prompt-export")
def export_mcharness_prompt(session_id: str, payload: McHarnessPromptExportRequest):
    run = _run_for_session(session_id)
    thread = _thread_for_session(session_id)
    prompt_text = export_captain_queue_item(payload.queue_item_id)
    artifact = _create_artifact(
        thread["thread_id"],
        "prompt_export",
        f"Prompt export {payload.queue_item_id}",
        prompt_text,
        f"Prompt export for {payload.queue_item_id}",
        "md",
    )
    if payload.mark_sent:
        _append_run_event(run["run_id"], "Prompt marked sent", f"Marked {payload.queue_item_id} as sent to the selected CLI lane.", "info", "artifact")
    return {
        "session_id": session_id,
        "run_id": run["run_id"],
        "queue_item_id": payload.queue_item_id,
        "prompt_text": prompt_text,
        "artifact": artifact,
    }


@mcharness_router.post("/sessions/{session_id}/runner-intent")
def post_mcharness_runner_intent(session_id: str, payload: McHarnessRunnerIntentRequest):
    """Dry-run only preview. Computes would-be command, prompt/transcript paths, safety policy.
    Never executes any CLI, never starts tmux, never touches secrets. Rejects non-dry and unknown ids.
    """
    if payload.mode != "dry_run":
        raise HTTPException(status_code=400, detail="Only dry_run mode is supported. Real execution is disabled by policy.")

    # Validate lane (known only; allow manual + implemented; reject unknown. Placeholders will show disabled.)
    lane = next((entry for entry in AGENT_LANES if entry["lane_id"] == payload.lane_id), None)
    if lane is None:
        raise HTTPException(status_code=400, detail=f"Unknown agent lane: {payload.lane_id}")

    # Validate repo by id (name or full path match on allowlist only)
    repo_path: Optional[Path] = None
    for p in SAFE_REPO_PATHS:
        if p.name == payload.repo_id or str(p) == payload.repo_id:
            repo_path = p
            break
    if repo_path is None:
        raise HTTPException(status_code=400, detail=f"Unknown repo_id (must be allowlisted): {payload.repo_id}")

    # Validate session exists (rejects missing/invalid)
    _ = _thread_for_session(session_id)

    cwd = str(repo_path)
    pid = payload.prompt_artifact_id or payload.queue_item_id or "head"
    prompt_file_path = str(ARTIFACT_BODY_ROOT / session_id / f"prompt-{pid}.md")
    transcript_file_path = str(ARTIFACT_BODY_ROOT / session_id / "transcript.txt")

    if payload.lane_id == "manual_paste":
        command_preview = (
            f"MANUAL: cd {cwd} && cat {prompt_file_path}  # run your local CLI in cwd, then POST transcript to /sessions/{session_id}/manual-result"
        )
    elif payload.lane_id == "codex_cli":
        command_preview = f"codex exec --cd {cwd} --output-last-message {transcript_file_path} < {prompt_file_path}  # (gated real; requires MCHARNESS_*_RUNNER_ENABLED=true for both tmux+codex; non-int or tmux attach)"
    elif payload.lane_id == "agy_cli":
        command_preview = f"agy --prompt {prompt_file_path}  # (dry-run preview only; cwd={cwd}; real launch disabled)"
    else:
        command_preview = f"# {payload.lane_id} would read {prompt_file_path} (placeholder lane; controlled_run_disabled)"

    safety_policy = {
        "allowlisted_lane": True,
        "allowlisted_repo": True,
        "arbitrary_shell_disabled": True,
        "public_real_agent_launch_disabled": True,
        "tmux_runner_enabled": _tmux_runner_enabled(),
    }
    notes = [
        "dry_run preview only. No CLI subprocess, no tmux session, no secret inspection, no network to providers.",
        "Controlled runner (real execution) is disabled in this public cockpit.",
    ]

    resp = {
        "ok": True,
        "real_execution_enabled": False,
        "lane_id": payload.lane_id,
        "repo_id": payload.repo_id,
        "session_id": session_id,
        "cwd": cwd,
        "prompt_file_path": prompt_file_path,
        "transcript_file_path": transcript_file_path,
        "command_preview": command_preview,
        "safety_policy": safety_policy,
        "notes": notes,
    }

    # May persist a runner_intent artifact (safe, read-oriented preview)
    try:
        _create_artifact(
            session_id,
            "runner_intent",
            f"runner-intent-{payload.lane_id}",
            json.dumps(resp, indent=2),
            "Dry-run runner intent preview (no execution performed)",
            "json",
        )
    except Exception:
        # preview response still valid even if artifact registration skipped
        pass

    return resp


@mcharness_router.post("/sessions/{session_id}/runner/start")
def post_mcharness_runner_start(session_id: str, payload: McHarnessRunnerStartRequest):
    """Start controlled runner for allowlisted lane (only fake_test_lane by default; real disabled).
    Validates session, lane (known), repo (allowlist), uses backend generated paths/names/cmd only.
    """
    thread = _thread_for_session(session_id)
    lane = next((entry for entry in AGENT_LANES if entry["lane_id"] == payload.lane_id), None)
    if lane is None:
        raise HTTPException(status_code=400, detail=f"Unknown agent lane: {payload.lane_id}")

    if payload.lane_id == "codex_cli":
        if not (_tmux_runner_enabled() and _codex_runner_enabled()):
            raise HTTPException(
                status_code=403,
                detail="Controlled Codex runner disabled (requires BOTH MCHARNESS_TMUX_RUNNER_ENABLED=true AND MCHARNESS_CODEX_RUNNER_ENABLED=true). For personal manual smoke only; no automated real Codex.",
            )
    elif payload.lane_id != "fake_test_lane" and not _tmux_runner_enabled():
        raise HTTPException(
            status_code=403,
            detail="Controlled runner disabled (MCHARNESS_TMUX_RUNNER_ENABLED=false). Only fake_test_lane supported for tests/proof.",
        )
    if payload.lane_id != "fake_test_lane" and payload.lane_id != "codex_cli":
        raise HTTPException(status_code=400, detail="Controlled run for this lane not implemented yet (only codex_cli + fake_test_lane).")

    # map repo_id to allowlisted path (id or full)
    repo_path: Optional[Path] = None
    for p in SAFE_REPO_PATHS:
        if p.name == payload.repo_id or str(p) == payload.repo_id:
            repo_path = p
            break
    if repo_path is None:
        raise HTTPException(status_code=400, detail=f"Unknown repo_id (must be allowlisted): {payload.repo_id}")

    runner_id = f"run_{uuid.uuid4().hex[:8]}"
    safe_name = _tmux_session_name(session_id, runner_id)
    pid = payload.prompt_artifact_id or payload.queue_item_id or "head"
    prompt_path = str(ARTIFACT_BODY_ROOT / session_id / f"prompt-{pid}.md")
    trans_path = str(ARTIFACT_BODY_ROOT / session_id / f"transcript-runner-{runner_id}.txt")

    state: dict[str, Any] = {
        "session_id": session_id,
        "runner_id": runner_id,
        "lane_id": payload.lane_id,
        "repo_id": payload.repo_id,
        "queue_item_id": payload.queue_item_id,
        "prompt_artifact_id": payload.prompt_artifact_id,
        "status": "starting",
        "tmux_session_name": safe_name,
        "prompt_file_path": prompt_path,
        "transcript_file_path": trans_path,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stopped_at": None,
        "exit_code": None,
        "safety_policy": {
            "allowlisted_lane": True,
            "allowlisted_repo": True,
            "tmux_runner_enabled": _tmux_runner_enabled(),
            "codex_runner_enabled": _codex_runner_enabled() if payload.lane_id == "codex_cli" else False,
            "real_provider": payload.lane_id == "codex_cli",
            "arbitrary_shell_disabled": True,
            "public_real_agent_launch_disabled": True,
        },
        "notes": [f"gated tmux runner; lane={payload.lane_id} (codex real only with both flags; fake for tests)"],
    }
    _save_runner_state(state)

    if payload.lane_id == "codex_cli":
        state = _start_codex_runner(state, str(repo_path))
    else:
        # fake
        state = _start_fake_runner(state)
    _save_runner_state(state)

    # event for audit/proof
    try:
        run = _run_for_session(session_id)
        _append_run_event(run["run_id"], "Runner started", f"Started {runner_id} lane={payload.lane_id}", "info", "runner")
    except Exception:
        pass

    return state


@mcharness_router.get("/sessions/{session_id}/runner/status")
def get_mcharness_runner_status(session_id: str):
    state = _load_runner_state(session_id)
    if not state:
        return {"status": "disabled", "notes": ["no runner for this session (or never started)"]}
    name = state.get("tmux_session_name")
    if name and state.get("status") in ("running", "starting"):
        has = _safe_cmd(["tmux", "has-session", "-t", name], timeout=1.0)
        if has is None or has.returncode != 0:
            state["status"] = "exited"
            # capture final transcript if not already
            final = _get_tmux_transcript(name)
            if final:
                try:
                    Path(state["transcript_file_path"]).write_text(final, encoding="utf-8")
                except Exception:
                    pass
            _save_runner_state(state)
    return state


@mcharness_router.post("/sessions/{session_id}/runner/stop")
def post_mcharness_runner_stop(session_id: str):
    state = _load_runner_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="No runner state for session")
    name = state.get("tmux_session_name")
    if name:
        _stop_tmux(name)
    state["status"] = "stopped"
    state["stopped_at"] = datetime.now(timezone.utc).isoformat()
    state["notes"].append("stopped by operator")
    _save_runner_state(state)
    try:
        run = _run_for_session(session_id)
        _append_run_event(run.get("run_id", ""), "Runner stopped", f"Stopped runner {state.get('runner_id')}", "info", "runner")
    except Exception:
        pass
    return state


@mcharness_router.get("/sessions/{session_id}/runner/transcript")
def get_mcharness_runner_transcript(session_id: str):
    state = _load_runner_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="No runner for session")
    p = Path(state["transcript_file_path"])
    text = ""
    if p.exists():
        text = p.read_text(encoding="utf-8")
    else:
        name = state.get("tmux_session_name")
        if name:
            text = _get_tmux_transcript(name)
    return {
        "session_id": session_id,
        "runner_id": state.get("runner_id"),
        "lane_id": state.get("lane_id"),
        "status": state.get("status"),
        "transcript_path": str(p),
        "transcript": text,
    }


@mcharness_router.post("/sessions/{session_id}/runner/transcript-to-evidence")
def post_mcharness_runner_transcript_to_evidence(session_id: str):
    """Save current runner transcript as evidence artifact (usable with proof gates)."""
    state = _load_runner_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="No runner for session")
    p = Path(state["transcript_file_path"])
    text = p.read_text(encoding="utf-8") if p.exists() else _get_tmux_transcript(state.get("tmux_session_name", ""))
    if not text:
        text = "(no transcript captured yet)"

    artifact = _create_artifact(
        session_id,
        "runner_transcript",
        f"runner-transcript-{state.get('runner_id')}",
        text,
        "transcript from gated tmux runner",
        "txt",
    )
    # also as evidence for gate flow (consistent with manual-result)
    ev = _create_artifact(
        session_id,
        "evidence",
        "Runner transcript evidence",
        text[:2000] + ("\n... (truncated)" if len(text) > 2000 else ""),
        "Saved runner transcript as evidence",
        "md",
    )
    try:
        run = _run_for_session(session_id)
        _append_run_event(run["run_id"], "Runner transcript to evidence", f"Saved transcript for {state.get('runner_id')} as evidence", "info", "evidence")
    except Exception:
        pass
    return {"ok": True, "artifact": artifact, "evidence_artifact": ev, "session_id": session_id}


@mcharness_router.post("/sessions/{session_id}/manual-result")
def post_mcharness_manual_result(session_id: str, payload: McHarnessManualResultRequest):
    thread = _thread_for_session(session_id)
    run = _run_for_session(session_id)
    metadata = thread.get("metadata") or {}
    artifacts: list[dict[str, Any]] = []
    transcript_text = payload.transcript or payload.summary
    result_kind = "manual_result" if metadata.get("agent_lane") == "manual_paste" else "cli_transcript"
    artifacts.append(
        _create_artifact(
            thread["thread_id"],
            result_kind,
            "CLI transcript" if result_kind == "cli_transcript" else "Manual result",
            transcript_text,
            payload.summary,
            "md",
        )
    )
    artifacts.append(
        _create_artifact(
            thread["thread_id"],
            "evidence",
            "Evidence record",
            payload.summary + "\n",
            payload.summary,
            "md",
        )
    )
    if payload.git_status:
        artifacts.append(
            _create_artifact(
                thread["thread_id"],
                "git_status",
                "Git status",
                payload.git_status,
                "Manual git status capture",
                "txt",
            )
        )
    if payload.git_diff_summary:
        artifacts.append(
            _create_artifact(
                thread["thread_id"],
                "git_diff_summary",
                "Git diff summary",
                payload.git_diff_summary,
                "Manual git diff summary capture",
                "txt",
            )
        )
    if payload.test_output:
        artifacts.append(
            _create_artifact(
                thread["thread_id"],
                "test_output",
                "Test output",
                payload.test_output,
                "Manual test output capture",
                "txt",
            )
        )
    if payload.assignment_id:
        record_captain_assignment_evidence(
            run["run_id"],
            payload.assignment_id,
            CaptainAssignmentEvidenceRequest(
                evidence_summary=payload.summary if not payload.transcript else f"{payload.summary}\n\nTranscript:\n{payload.transcript}",
                source_ref=payload.source_ref,
                artifact_refs=[artifact["path"] for artifact in artifacts],
                verdict=payload.verdict,
            ),
        )
        if payload.complete_assignment:
            complete_captain_assignment(
                run["run_id"],
                payload.assignment_id,
                CaptainAssignmentCompleteRequest(
                    evidence_summary=payload.summary,
                    output_summary=transcript_text,
                ),
            )
    else:
        WORKBENCH_STORE.add_run_evidence(
            run["run_id"],
            WorkbenchEvidenceRecordCreateRequest(
                title="Manual result evidence",
                summary=payload.summary,
                source_type="manual",
                source_ref=payload.source_ref,
                verdict=payload.verdict,
            ),
        )
    _append_run_event(run["run_id"], "Manual result captured", f"Captured {result_kind} for lane {metadata.get('agent_lane', 'unknown')}.", "success", "evidence")
    return {
        "session_id": session_id,
        "run_id": run["run_id"],
        "artifacts": artifacts,
        "evidence_summary": payload.summary,
    }


@mcharness_router.post("/sessions/{session_id}/gate-decision")
def post_mcharness_gate_decision(session_id: str, payload: McHarnessGateDecisionRequest):
    thread = _thread_for_session(session_id)
    run = _run_for_session(session_id)
    gates = WORKBENCH_STORE.list_proof_gates(run["run_id"])
    gate = next((item for item in gates if item.status == "open"), gates[0] if gates else None)
    if gate is None:
        raise HTTPException(status_code=404, detail=f"No proof gate found for session: {session_id}")
    updated_run = WORKBENCH_STORE.decide_run_proof_gate(
        gate.gate_id,
        WorkbenchRunProofGateDecisionRequest(
            decision=payload.decision,
            actor="operator",
            note=payload.note,
        ),
    )
    artifact = _create_artifact(
        thread["thread_id"],
        "gate_decision",
        "Gate decision",
        "\n".join(
            [
                f"Gate id: {gate.gate_id}",
                f"Decision: {payload.decision}",
                f"Note: {payload.note or '(none)'}",
            ]
        ),
        payload.note or payload.decision,
        "md",
    )
    continuation = None
    if payload.continue_after:
        continuation = continue_captain_run(run["run_id"])
    run_summary = _create_run_summary_artifact(thread, updated_run, f"Gate {payload.decision} recorded.")
    return {
        "session_id": session_id,
        "run": updated_run,
        "gate_id": gate.gate_id,
        "decision": payload.decision,
        "artifact": artifact,
        "continuation": continuation,
        "run_summary_artifact": run_summary,
    }


@mcharness_router.get("/sessions/{session_id}/artifacts")
def get_mcharness_session_artifacts(session_id: str):
    _thread_for_session(session_id)
    artifacts = [
        artifact.model_dump(mode="json")
        for artifact in WORKBENCH_STORE.list_artifacts()
        if artifact.thread_id == session_id
    ]
    artifacts.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return {
        "session_id": session_id,
        "artifacts": artifacts,
    }


@mcharness_router.get("/sessions/{session_id}/git-status")
def get_mcharness_session_git_status(session_id: str):
    thread = _thread_for_session(session_id)
    return _capture_git_status_artifacts(thread)


@legacy_router.post("/api/mctable/local/dispatch-launch")
def disabled_legacy_launch_route():
    raise HTTPException(status_code=400, detail="deprecated/disabled legacy launch route")
