from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .contracts import (
    CaptainRun,
    CaptainTemplate,
    EvidenceRecord,
    HardGate,
    MinionTask,
    PromptQueueItem,
    ScopedCommitPlan,
)

MCTABLE_ROOT = Path("_mctable")
CAPTAIN_ROOT = MCTABLE_ROOT / "captain"
RUNS_DIR = CAPTAIN_ROOT / "runs"
FILE_LOCK = threading.Lock()

router = APIRouter(prefix="/captain", tags=["marius-desktop-captain"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def _load_run(run_id: str) -> CaptainRun:
    path = _run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(run_id)
    return CaptainRun.model_validate_json(path.read_text(encoding="utf-8"))


def _save_run(run: CaptainRun) -> CaptainRun:
    _ensure_dirs()
    _run_path(run.run_id).write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run


def _update_run(run_id: str, updater) -> CaptainRun:
    with FILE_LOCK:
        run = _load_run(run_id)
        updated = updater(run)
        updated.updated_at = _now()
        return _save_run(updated)


class CaptainRunCreateRequest(BaseModel):
    objective: str
    next_action: str = "inspect"
    prompt_queue: list[PromptQueueItem] = Field(default_factory=list)
    minion_tasks: list[MinionTask] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    hard_gates: list[HardGate] = Field(default_factory=list)
    scoped_commit_plan: Optional[ScopedCommitPlan] = None
    planned_acceptance_commands: list[str] = Field(default_factory=list)


class EvidenceCreateRequest(BaseModel):
    kind: Optional[str] = None
    summary: str
    status: Optional[str] = None
    command_text: Optional[str] = None
    details: Optional[str] = None
    captured_by: str
    artifacts: list[str] = Field(default_factory=list)


class GateCreateRequest(BaseModel):
    kind: str
    reason: str
    triggered_by: str


class GateDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "edit_state"]
    actor: str
    reviewer_note: Optional[str] = None


class CaptainNextRequest(BaseModel):
    next_action: str
    planned_acceptance_commands: list[str] = Field(default_factory=list)
    command_execution_request: bool = False


class CaptainTemplateRunRequest(BaseModel):
    template: CaptainTemplate
    next_action: str = "inspect"
    command_execution_request: bool = False


def _safe_gate(reason: str, triggered_by: str = "captain") -> HardGate:
    return HardGate(
        gate_id=f"gate_{uuid.uuid4().hex[:8]}",
        kind="safety",
        reason=reason,
        triggered_by=triggered_by,
        blocked=True,
        created_at=_now(),
    )


def _template_library() -> dict[str, CaptainTemplate]:
    return {
        "release_qa": CaptainTemplate(
            template_id="release_qa",
            title="Release QA",
            objective="Verify the release candidate and collect proof.",
            prompt_queue=[
                PromptQueueItem(
                    prompt_id="review_status",
                    title="Review backend status and capabilities",
                    notes="Check the local API, worker runner, and cockpit target wording.",
                ),
                PromptQueueItem(
                    prompt_id="compile_report",
                    title="Compile the release report",
                    notes="Summarize what was proven and what remains unproven.",
                ),
            ],
            minion_tasks=[
                MinionTask(
                    minion_id="status_auditor",
                    role="auditor",
                    scope="Review the live status and proof surface.",
                    files=["src/marius_desktop/api.py", "web/mctable-studio/cockpit.html"],
                    notes="Keep the scope to the local desktop surface.",
                ),
                MinionTask(
                    minion_id="report_writer",
                    role="scribe",
                    scope="Draft the final report and proof summary.",
                    files=["docs/release_checklist.md", "docs/demo_script.md"],
                    notes="Use only verified backend results.",
                ),
            ],
            hard_gates=[
                _safe_gate("Keep the work local, scoped, and free of runtime artifacts."),
            ],
            scoped_commit_plan=ScopedCommitPlan(
                commit_message="docs(marius-desktop): prepare release proof",
                files=["docs/release_checklist.md", "docs/demo_script.md"],
            ),
            planned_acceptance_commands=[
                "python -m pytest -q tests/test_marius_desktop_captain.py tests/test_marius_desktop_api.py",
                "PYTHONPATH=. python scripts/verify_marius_desktop_backend.py",
            ],
        ),
        "ui_polish": CaptainTemplate(
            template_id="ui_polish",
            title="UI Polish",
            objective="Tune cockpit wording and status presentation.",
            prompt_queue=[
                PromptQueueItem(
                    prompt_id="check_status_strip",
                    title="Check the status strip wording",
                    notes="Use the live backend target and current service state.",
                ),
                PromptQueueItem(
                    prompt_id="review_shell",
                    title="Review the desktop shell copy",
                    notes="Keep the wrapper honest and local-only.",
                ),
            ],
            minion_tasks=[
                MinionTask(
                    minion_id="cockpit_editor",
                    role="designer",
                    scope="Polish the cockpit display text.",
                    files=["web/mctable-studio/cockpit.html"],
                ),
                MinionTask(
                    minion_id="shell_editor",
                    role="designer",
                    scope="Polish the desktop shell display text.",
                    files=["src-tauri/frontend/index.html"],
                ),
            ],
            hard_gates=[_safe_gate("Keep the work local and avoid runtime artifacts.")],
            planned_acceptance_commands=[
                "python -m pytest -q tests/test_marius_desktop_cockpit_static.py tests/test_marius_desktop_tauri_shell.py",
            ],
        ),
        "docs_audit": CaptainTemplate(
            template_id="docs_audit",
            title="Docs Audit",
            objective="Cross-check the public docs against verified backend behavior.",
            prompt_queue=[
                PromptQueueItem(
                    prompt_id="compare_docs",
                    title="Compare docs and live behavior",
                    notes="Confirm that the docs match the verified API and shell behavior.",
                ),
                PromptQueueItem(
                    prompt_id="note_gaps",
                    title="Record honest gaps",
                    notes="List the remaining unproven items without overstating them.",
                ),
            ],
            minion_tasks=[
                MinionTask(
                    minion_id="doc_checker",
                    role="auditor",
                    scope="Audit the release docs for accuracy.",
                    files=["docs/architecture.md", "docs/demo_script.md", "docs/marius_agent_desktop_captain_mode.md"],
                ),
            ],
            hard_gates=[_safe_gate("Keep the audit read-only and local.")],
            scoped_commit_plan=ScopedCommitPlan(
                commit_message="docs(marius-desktop): audit release copy",
                files=["docs/architecture.md", "docs/demo_script.md", "docs/marius_agent_desktop_captain_mode.md"],
            ),
            planned_acceptance_commands=[
                "python -m pytest -q tests/test_marius_desktop_api.py tests/test_marius_desktop_captain.py",
            ],
        ),
        "test_triage": CaptainTemplate(
            template_id="test_triage",
            title="Test Triage",
            objective="Separate passing checks from failing checks and record the delta.",
            prompt_queue=[
                PromptQueueItem(
                    prompt_id="run_focus",
                    title="Run the focused acceptance set",
                    notes="Use the smallest test slice that proves the change.",
                ),
                PromptQueueItem(
                    prompt_id="record_delta",
                    title="Record the test delta",
                    notes="Capture only verified failures and fixes.",
                ),
            ],
            minion_tasks=[
                MinionTask(
                    minion_id="test_runner",
                    role="qa",
                    scope="Run the focused backend tests.",
                    files=["tests/test_marius_desktop_api.py", "tests/test_marius_desktop_captain.py"],
                ),
            ],
            hard_gates=[_safe_gate("Do not widen scope beyond the local test slice.")],
            planned_acceptance_commands=[
                "python -m pytest -q tests/test_marius_desktop_captain.py tests/test_marius_desktop_api.py tests/test_marius_desktop_contracts.py tests/test_marius_desktop_graph.py",
            ],
        ),
        "marathon_queue": CaptainTemplate(
            template_id="marathon_queue",
            title="Marathon Queue",
            objective="Prepare the next prompt queue for a long local sprint.",
            prompt_queue=[
                PromptQueueItem(
                    prompt_id="load_queue",
                    title="Load the next queue item",
                    notes="Work one prompt at a time and keep the scope narrow.",
                ),
                PromptQueueItem(
                    prompt_id="verify_commit",
                    title="Verify the scoped commit",
                    notes="Stage only the allowed files and confirm the tree is clean.",
                ),
            ],
            minion_tasks=[
                MinionTask(
                    minion_id="queue_keeper",
                    role="coordinator",
                    scope="Track prompt order and commit boundaries.",
                    files=["docs/marius_agent_desktop_captain_mode.md", "docs/architecture.md"],
                ),
            ],
            hard_gates=[_safe_gate("Keep the sprint local and avoid runtime artifacts.")],
            planned_acceptance_commands=[
                "python -m pytest -q tests/test_marius_desktop_captain.py",
                "ruff check src/marius_desktop tests/test_marius_desktop_* scripts/fake_worker.py scripts/verify_marius_desktop_backend.py scripts/demo_marius_desktop.py",
            ],
        ),
    }


CAPTAIN_TEMPLATES = _template_library()


def _template_text_fields(template: CaptainTemplate) -> list[str]:
    values: list[str] = [
        template.template_id,
        template.title,
        template.objective,
        template.notes or "",
    ]
    for item in template.prompt_queue:
        values.extend([item.prompt_id, item.title, item.prompt_path or "", item.commit_message or "", item.notes or ""])
    for task in template.minion_tasks:
        values.extend([task.minion_id, task.role or "", task.scope, task.notes or ""])
        values.extend(task.files)
    for gate in template.hard_gates:
        values.extend([gate.gate_id, gate.kind, gate.reason, gate.triggered_by])
    if template.scoped_commit_plan:
        values.extend(
            [
                template.scoped_commit_plan.commit_message,
                template.scoped_commit_plan.notes or "",
            ]
        )
        values.extend(template.scoped_commit_plan.files)
    values.extend(template.planned_acceptance_commands)
    return [value for value in values if value]


def _reject_forbidden_template_content(template: CaptainTemplate) -> None:
    blocked_phrases = [
        "shell=true",
        "dangerously-skip-permissions",
        "--yolo",
        "--always-approve",
        "public worker launch",
        "real external agent launch",
        "rm -rf",
        "deploy",
        "secret",
        "credential",
        "password",
        "token",
        "grok",
        "codex",
        "claude",
        "agy",
    ]
    for text in _template_text_fields(template):
        lowered = text.lower()
        for phrase in blocked_phrases:
            if phrase in lowered:
                raise HTTPException(
                    status_code=400,
                    detail=f"Template content is not allowed: '{phrase}'",
                )


@router.get("/runs", response_model=list[CaptainRun])
def list_captain_runs() -> list[CaptainRun]:
    _ensure_dirs()
    runs: list[CaptainRun] = []
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            runs.append(CaptainRun.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return runs


@router.get("/templates", response_model=list[CaptainTemplate])
def list_captain_templates() -> list[CaptainTemplate]:
    return [template.model_copy(deep=True) for template in CAPTAIN_TEMPLATES.values()]


@router.get("/templates/{template_id}", response_model=CaptainTemplate)
def get_captain_template(template_id: str) -> CaptainTemplate:
    try:
        return CAPTAIN_TEMPLATES[template_id].model_copy(deep=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Captain template {template_id} not found.") from exc


@router.post("/runs/from-template", response_model=CaptainRun)
def create_captain_run_from_template(req: CaptainTemplateRunRequest) -> CaptainRun:
    if req.command_execution_request:
        raise HTTPException(
            status_code=501,
            detail="not_implemented: command execution is blocked; Captain Mode stores planned acceptance commands as text only.",
        )

    _reject_forbidden_template_content(req.template)
    template = req.template.model_copy(deep=True)
    now = _now()
    run = CaptainRun(
        run_id=f"run_{uuid.uuid4().hex[:8]}",
        objective=template.objective,
        status="active",
        prompt_queue=template.prompt_queue,
        minion_tasks=template.minion_tasks,
        evidence_records=[],
        hard_gates=template.hard_gates,
        scoped_commit_plan=template.scoped_commit_plan,
        next_action=req.next_action,
        planned_acceptance_commands=template.planned_acceptance_commands,
        created_at=now,
        updated_at=now,
    )
    return _save_run(run)


@router.post("/runs", response_model=CaptainRun)
def create_captain_run(req: CaptainRunCreateRequest) -> CaptainRun:
    now = _now()
    run = CaptainRun(
        run_id=f"run_{uuid.uuid4().hex[:8]}",
        objective=req.objective,
        status="active",
        prompt_queue=req.prompt_queue,
        minion_tasks=req.minion_tasks,
        evidence_records=req.evidence_records,
        hard_gates=req.hard_gates,
        scoped_commit_plan=req.scoped_commit_plan,
        next_action=req.next_action,
        planned_acceptance_commands=req.planned_acceptance_commands,
        created_at=now,
        updated_at=now,
    )
    return _save_run(run)


@router.get("/runs/{run_id}", response_model=CaptainRun)
def get_captain_run(run_id: str) -> CaptainRun:
    try:
        return _load_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Captain run {run_id} not found.") from exc


@router.post("/runs/{run_id}/evidence", response_model=CaptainRun)
def add_evidence(run_id: str, req: EvidenceCreateRequest) -> CaptainRun:
    def _append(run: CaptainRun) -> CaptainRun:
        run.evidence_records.append(
            EvidenceRecord(
                evidence_id=f"ev_{uuid.uuid4().hex[:8]}",
                kind=req.kind,
                summary=req.summary,
                status=req.status,
                command_text=req.command_text,
                details=req.details,
                captured_by=req.captured_by,
                artifacts=req.artifacts,
                captured_at=_now(),
            )
        )
        return run

    try:
        return _update_run(run_id, _append)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Captain run {run_id} not found.") from exc


@router.post("/runs/{run_id}/gate", response_model=CaptainRun)
def add_gate(run_id: str, req: GateCreateRequest) -> CaptainRun:
    def _block(run: CaptainRun) -> CaptainRun:
        run.hard_gates.append(
            HardGate(
                gate_id=f"gate_{uuid.uuid4().hex[:8]}",
                kind=req.kind,
                reason=req.reason,
                triggered_by=req.triggered_by,
                blocked=True,
                created_at=_now(),
            )
        )
        run.status = "blocked"
        return run

    try:
        return _update_run(run_id, _block)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Captain run {run_id} not found.") from exc


@router.post("/runs/{run_id}/gates/{gate_id}/decision", response_model=CaptainRun)
def record_gate_decision(run_id: str, gate_id: str, req: GateDecisionRequest) -> CaptainRun:
    def _record(run: CaptainRun) -> CaptainRun:
        gate = next((item for item in run.hard_gates if item.gate_id == gate_id), None)
        if gate is None:
            raise HTTPException(status_code=404, detail=f"Captain gate {gate_id} not found.")
        gate.decision = req.decision
        gate.decision_actor = req.actor
        gate.decision_note = req.reviewer_note
        gate.decided_at = _now()
        return run

    try:
        return _update_run(run_id, _record)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Captain run {run_id} not found.") from exc


@router.post("/runs/{run_id}/next", response_model=CaptainRun)
def set_next_action(run_id: str, req: CaptainNextRequest) -> CaptainRun:
    if req.command_execution_request:
        raise HTTPException(
            status_code=501,
            detail="not_implemented: command execution is blocked; Captain Mode stores planned acceptance commands as text only.",
        )

    def _advance(run: CaptainRun) -> CaptainRun:
        if run.hard_gates:
            raise HTTPException(status_code=409, detail="Continuation blocked by hard gate.")
        run.next_action = req.next_action
        run.planned_acceptance_commands = req.planned_acceptance_commands
        return run

    try:
        return _update_run(run_id, _advance)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Captain run {run_id} not found.") from exc
