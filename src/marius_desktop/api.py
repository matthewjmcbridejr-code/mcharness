import os
import subprocess
import uuid
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


def _repo_entries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in SAFE_REPO_PATHS:
        rows.append(
            {
                "repo_id": path.name,
                "label": path.name,
                "path": str(path),
                "exists": path.exists(),
                "git_dir_present": (path / ".git").exists(),
            }
        )
    return rows


def _lane_entries() -> list[dict[str, Any]]:
    return list(AGENT_LANES)


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
