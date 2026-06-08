from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .contracts import EvidenceRecord, HardGate, MinionTask, PromptQueueItem, ScopedCommitPlan

MCTABLE_ROOT = Path("_mctable")
WORKBENCH_ROOT = MCTABLE_ROOT / "workbench"
FILE_LOCK = threading.Lock()

SAFE_SLUG = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$"


class WorkbenchError(ValueError):
    pass


class WorkbenchAgent(BaseModel):
    agent_id: str
    name: str
    role: str = "operator"
    status: Literal["active", "paused", "disabled"] = "active"
    safety_profile_id: str = "operator_local"
    allowed_threads: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkbenchThread(BaseModel):
    thread_id: str
    agent_id: Optional[str] = None
    title: str
    objective: str
    status: Literal["open", "paused", "blocked", "closed"] = "open"
    next_action: str = "inspect"
    prompt_queue: list[PromptQueueItem] = Field(default_factory=list)
    minion_tasks: list[MinionTask] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    hard_gates: list[HardGate] = Field(default_factory=list)
    scoped_commit_plan: Optional[ScopedCommitPlan] = None
    planned_acceptance_commands: list[str] = Field(default_factory=list)
    recovery_hint: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkbenchMessage(BaseModel):
    message_id: str
    thread_id: str
    author: str
    kind: Literal["planning", "note", "evidence", "system", "command_request"] = "note"
    content: str
    status: Literal["recorded", "blocked"] = "recorded"
    recovery_hint: Optional[str] = None
    created_at: datetime


class WorkbenchSkill(BaseModel):
    skill_id: str
    title: str
    description: str
    path: Optional[str] = None
    enabled: bool = True
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkbenchMemory(BaseModel):
    memory_id: str
    scope: str
    summary: str
    source: str
    compacted: bool = False
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkbenchArtifact(BaseModel):
    artifact_id: str
    thread_id: Optional[str] = None
    kind: str
    title: str
    path: str
    summary: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkbenchTool(BaseModel):
    name: str
    category: str
    status: Literal["available", "disabled", "not_implemented"] = "available"
    summary: str
    local_only: bool = True
    fake_worker_only: bool = True
    real_agent_launch_disabled: bool = True
    arbitrary_command_execution_disabled: bool = True
    recovery_hint: Optional[str] = None


class SafetyProfile(BaseModel):
    profile_id: str
    title: str
    summary: str
    local_only: bool = True
    fake_worker_only: bool = True
    real_agent_launch_disabled: bool = True
    arbitrary_command_execution_disabled: bool = True
    mcp_local_only: bool = True
    shell_enabled: bool = False
    notes: Optional[str] = None


class WorkbenchAgentCreateRequest(BaseModel):
    agent_id: str = Field(pattern=SAFE_SLUG)
    name: str = Field(min_length=1)
    role: str = "operator"
    status: Literal["active", "paused", "disabled"] = "active"
    safety_profile_id: str = "operator_local"
    allowed_threads: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class WorkbenchThreadCreateRequest(BaseModel):
    thread_id: str = Field(pattern=SAFE_SLUG)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    agent_id: Optional[str] = None
    status: Literal["open", "paused", "blocked", "closed"] = "open"
    next_action: str = "inspect"
    prompt_queue: list[PromptQueueItem] = Field(default_factory=list)
    minion_tasks: list[MinionTask] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    hard_gates: list[HardGate] = Field(default_factory=list)
    scoped_commit_plan: Optional[ScopedCommitPlan] = None
    planned_acceptance_commands: list[str] = Field(default_factory=list)
    recovery_hint: Optional[str] = None
    notes: Optional[str] = None


class WorkbenchMessageCreateRequest(BaseModel):
    author: str = Field(min_length=1)
    kind: Literal["planning", "note", "evidence", "system", "command_request"] = "note"
    content: str = Field(min_length=1)


class WorkbenchSkillCreateRequest(BaseModel):
    skill_id: str = Field(pattern=SAFE_SLUG)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    path: Optional[str] = None
    enabled: bool = True
    notes: Optional[str] = None


class WorkbenchMemoryCreateRequest(BaseModel):
    memory_id: str = Field(pattern=SAFE_SLUG)
    scope: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source: str = Field(min_length=1)
    compacted: bool = False
    notes: Optional[str] = None


class WorkbenchArtifactCreateRequest(BaseModel):
    artifact_id: str = Field(pattern=SAFE_SLUG)
    kind: str = Field(min_length=1)
    title: str = Field(min_length=1)
    path: str = Field(min_length=1)
    thread_id: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None


class WorkbenchProofGateCreateRequest(BaseModel):
    kind: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    triggered_by: str = Field(min_length=1)


class WorkbenchProofGateDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "edit_state"]
    actor: str = Field(min_length=1)
    reviewer_note: Optional[str] = None


DEFAULT_TOOLS: list[WorkbenchTool] = [
    WorkbenchTool(
        name="workbench_threads",
        category="workflow",
        summary="Local thread and message registry for supervised planning work.",
    ),
    WorkbenchTool(
        name="workbench_skills",
        category="workflow",
        summary="Local skill registry for repeatable operator workflows.",
    ),
    WorkbenchTool(
        name="workbench_memories",
        category="workflow",
        summary="Local memory records for review and continuity.",
    ),
    WorkbenchTool(
        name="workbench_artifacts",
        category="workflow",
        summary="Local artifact registry for proof, notes, and attachments.",
    ),
    WorkbenchTool(
        name="local_mcp",
        category="integration",
        summary="Local-only MCP tool layer.",
    ),
    WorkbenchTool(
        name="fake_worker_runner",
        category="execution",
        summary="Fake-worker-only execution surface for the current RC.",
    ),
]

DEFAULT_SAFETY_PROFILES: list[SafetyProfile] = [
    SafetyProfile(
        profile_id="operator_local",
        title="Operator Local",
        summary="Local-only supervised workflow profile with fake-worker-only execution.",
        notes="Real external agent launch is disabled.",
    ),
    SafetyProfile(
        profile_id="screenshot_sample",
        title="Screenshot Sample",
        summary="Preview profile for local cockpit screenshots and demos.",
        notes="Sample UI data is not executed.",
    ),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_id(value: str, field: str) -> str:
    import re

    if not re.match(SAFE_SLUG, value):
        raise WorkbenchError(f"invalid {field}: {value}")
    return value


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
        f.write("\n")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_model(path: Path, model: type[BaseModel]) -> BaseModel:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


class WorkbenchStore:
    def __init__(self, root: str | Path = WORKBENCH_ROOT, ensure_layout: bool = True) -> None:
        self.root = Path(root).resolve()
        if ensure_layout:
            self.ensure_layout()

    def ensure_layout(self) -> None:
        for directory in [
            "agents",
            "threads",
            "messages",
            "skills",
            "memories",
            "artifacts",
        ]:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        tools_path = self.root / "tools.json"
        if not tools_path.exists():
            _atomic_write_json(tools_path, [tool.model_dump(mode="json") for tool in DEFAULT_TOOLS])
        safety_path = self.root / "safety_profiles.json"
        if not safety_path.exists():
            _atomic_write_json(safety_path, [profile.model_dump(mode="json") for profile in DEFAULT_SAFETY_PROFILES])

    def _path(self, kind: str, item_id: str) -> Path:
        return self.root / kind / f"{item_id}.json"

    def _message_path(self, thread_id: str) -> Path:
        return self.root / "messages" / f"{thread_id}.jsonl"

    def _load_list_file(self, path: Path, model: type[BaseModel]) -> list[BaseModel]:
        if not path.exists():
            return []
        rows = _read_json(path)
        return [model.model_validate(item) for item in rows]

    def _save_list_file(self, path: Path, rows: list[BaseModel]) -> None:
        _atomic_write_json(path, [row.model_dump(mode="json") for row in rows])

    def _load_messages(self, thread_id: str) -> list[WorkbenchMessage]:
        path = self._message_path(thread_id)
        if not path.exists():
            return []
        rows: list[WorkbenchMessage] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(WorkbenchMessage.model_validate_json(line))
        return rows

    def _append_message(self, thread_id: str, message: WorkbenchMessage) -> None:
        path = self._message_path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(message.model_dump_json())
            f.write("\n")

    def _load_thread(self, thread_id: str) -> WorkbenchThread:
        path = self._path("threads", _safe_id(thread_id, "thread_id"))
        if not path.exists():
            raise WorkbenchError(f"thread not available: {thread_id}")
        return _load_model(path, WorkbenchThread)

    def _save_thread(self, thread: WorkbenchThread) -> WorkbenchThread:
        _atomic_write_json(self._path("threads", thread.thread_id), thread.model_dump(mode="json"))
        return thread

    def _thread_view(self, thread: WorkbenchThread) -> dict[str, Any]:
        messages = self._load_messages(thread.thread_id)
        blocked_gates = [gate for gate in thread.hard_gates if gate.blocked and gate.decision != "approve"]
        return {
            **thread.model_dump(mode="json"),
            "messages": [message.model_dump(mode="json") for message in messages],
            "message_count": len(messages),
            "proof_gate_count": len(thread.hard_gates),
            "blocked_gate_count": len(blocked_gates),
        }

    def list_agents(self) -> list[WorkbenchAgent]:
        self.ensure_layout()
        agents_dir = self.root / "agents"
        if not agents_dir.exists():
            return []
        rows: list[WorkbenchAgent] = []
        for path in sorted(agents_dir.glob("*.json")):
            try:
                rows.append(_load_model(path, WorkbenchAgent))
            except Exception:
                continue
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows

    def get_agent(self, agent_id: str) -> WorkbenchAgent:
        self.ensure_layout()
        path = self._path("agents", _safe_id(agent_id, "agent_id"))
        if not path.exists():
            raise WorkbenchError(f"agent not available: {agent_id}")
        return _load_model(path, WorkbenchAgent)

    def upsert_agent(self, payload: WorkbenchAgentCreateRequest) -> WorkbenchAgent:
        self.ensure_layout()
        _safe_id(payload.agent_id, "agent_id")
        if payload.safety_profile_id not in {profile.profile_id for profile in self.list_safety_profiles()}:
            raise WorkbenchError(f"safety profile not available: {payload.safety_profile_id}")
        agent = WorkbenchAgent(
            agent_id=payload.agent_id,
            name=payload.name,
            role=payload.role,
            status=payload.status,
            safety_profile_id=payload.safety_profile_id,
            allowed_threads=list(payload.allowed_threads),
            notes=payload.notes,
            created_at=_now(),
            updated_at=_now(),
        )
        _atomic_write_json(self._path("agents", agent.agent_id), agent.model_dump(mode="json"))
        return agent

    def list_threads(self) -> list[dict[str, Any]]:
        self.ensure_layout()
        threads_dir = self.root / "threads"
        if not threads_dir.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(threads_dir.glob("*.json")):
            try:
                thread = _load_model(path, WorkbenchThread)
            except Exception:
                continue
            rows.append(
                {
                    **thread.model_dump(mode="json"),
                    "message_count": len(self._load_messages(thread.thread_id)),
                    "proof_gate_count": len(thread.hard_gates),
                }
            )
        rows.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return rows

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        self.ensure_layout()
        return self._thread_view(self._load_thread(thread_id))

    def create_thread(self, payload: WorkbenchThreadCreateRequest) -> dict[str, Any]:
        self.ensure_layout()
        _safe_id(payload.thread_id, "thread_id")
        if self._path("threads", payload.thread_id).exists():
            raise WorkbenchError(f"thread already exists: {payload.thread_id}")
        if payload.agent_id is not None:
            self.get_agent(payload.agent_id)
        thread = WorkbenchThread(
            thread_id=payload.thread_id,
            agent_id=payload.agent_id,
            title=payload.title,
            objective=payload.objective,
            status=payload.status,
            next_action=payload.next_action,
            prompt_queue=list(payload.prompt_queue),
            minion_tasks=list(payload.minion_tasks),
            evidence_records=list(payload.evidence_records),
            hard_gates=list(payload.hard_gates),
            scoped_commit_plan=payload.scoped_commit_plan,
            planned_acceptance_commands=list(payload.planned_acceptance_commands),
            recovery_hint=payload.recovery_hint,
            notes=payload.notes,
            created_at=_now(),
            updated_at=_now(),
        )
        if thread.hard_gates and any(gate.blocked and gate.decision != "approve" for gate in thread.hard_gates):
            thread.status = "blocked"
        self._save_thread(thread)
        return self._thread_view(thread)

    def list_messages(self, thread_id: str) -> list[dict[str, Any]]:
        self.ensure_layout()
        self._load_thread(thread_id)
        return [message.model_dump(mode="json") for message in self._load_messages(thread_id)]

    def append_message(self, thread_id: str, payload: WorkbenchMessageCreateRequest) -> WorkbenchMessage:
        self.ensure_layout()
        thread = self._load_thread(thread_id)
        if payload.kind == "command_request":
            raise WorkbenchError("Command execution is disabled in Workbench Core.")
        message = WorkbenchMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            thread_id=thread.thread_id,
            author=payload.author,
            kind=payload.kind,
            content=payload.content,
            status="recorded",
            created_at=_now(),
        )
        self._append_message(thread.thread_id, message)
        thread.updated_at = _now()
        self._save_thread(thread)
        return message

    def add_proof_gate(self, thread_id: str, payload: WorkbenchProofGateCreateRequest) -> dict[str, Any]:
        self.ensure_layout()
        thread = self._load_thread(thread_id)
        gate = HardGate(
            gate_id=f"gate_{uuid.uuid4().hex[:8]}",
            kind=payload.kind,
            reason=payload.reason,
            triggered_by=payload.triggered_by,
            blocked=True,
            created_at=_now(),
        )
        thread.hard_gates.append(gate)
        thread.status = "blocked"
        thread.updated_at = _now()
        self._save_thread(thread)
        return self._thread_view(thread)

    def decide_proof_gate(self, thread_id: str, gate_id: str, payload: WorkbenchProofGateDecisionRequest) -> dict[str, Any]:
        self.ensure_layout()
        thread = self._load_thread(thread_id)
        gate = next((item for item in thread.hard_gates if item.gate_id == gate_id), None)
        if gate is None:
            raise WorkbenchError(f"gate not available: {gate_id}")
        gate.decision = payload.decision
        gate.decision_actor = payload.actor
        gate.decision_note = payload.reviewer_note
        gate.decided_at = _now()
        gate.blocked = payload.decision != "approve"
        thread.status = "blocked" if any(item.blocked and item.decision != "approve" for item in thread.hard_gates) else "open"
        thread.updated_at = _now()
        self._save_thread(thread)
        return self._thread_view(thread)

    def list_skills(self) -> list[WorkbenchSkill]:
        self.ensure_layout()
        skills_dir = self.root / "skills"
        rows: list[WorkbenchSkill] = []
        if not skills_dir.exists():
            return rows
        for path in sorted(skills_dir.glob("*.json")):
            try:
                rows.append(_load_model(path, WorkbenchSkill))
            except Exception:
                continue
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows

    def get_skill(self, skill_id: str) -> WorkbenchSkill:
        self.ensure_layout()
        path = self._path("skills", _safe_id(skill_id, "skill_id"))
        if not path.exists():
            raise WorkbenchError(f"skill not available: {skill_id}")
        return _load_model(path, WorkbenchSkill)

    def create_skill(self, payload: WorkbenchSkillCreateRequest) -> WorkbenchSkill:
        self.ensure_layout()
        _safe_id(payload.skill_id, "skill_id")
        if self._path("skills", payload.skill_id).exists():
            raise WorkbenchError(f"skill already exists: {payload.skill_id}")
        skill = WorkbenchSkill(
            skill_id=payload.skill_id,
            title=payload.title,
            description=payload.description,
            path=payload.path,
            enabled=payload.enabled,
            notes=payload.notes,
            created_at=_now(),
            updated_at=_now(),
        )
        _atomic_write_json(self._path("skills", skill.skill_id), skill.model_dump(mode="json"))
        return skill

    def list_memories(self) -> list[WorkbenchMemory]:
        self.ensure_layout()
        memories_dir = self.root / "memories"
        rows: list[WorkbenchMemory] = []
        if not memories_dir.exists():
            return rows
        for path in sorted(memories_dir.glob("*.json")):
            try:
                rows.append(_load_model(path, WorkbenchMemory))
            except Exception:
                continue
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows

    def create_memory(self, payload: WorkbenchMemoryCreateRequest) -> WorkbenchMemory:
        self.ensure_layout()
        _safe_id(payload.memory_id, "memory_id")
        if self._path("memories", payload.memory_id).exists():
            raise WorkbenchError(f"memory already exists: {payload.memory_id}")
        memory = WorkbenchMemory(
            memory_id=payload.memory_id,
            scope=payload.scope,
            summary=payload.summary,
            source=payload.source,
            compacted=payload.compacted,
            notes=payload.notes,
            created_at=_now(),
            updated_at=_now(),
        )
        _atomic_write_json(self._path("memories", memory.memory_id), memory.model_dump(mode="json"))
        return memory

    def list_artifacts(self) -> list[WorkbenchArtifact]:
        self.ensure_layout()
        artifacts_dir = self.root / "artifacts"
        rows: list[WorkbenchArtifact] = []
        if not artifacts_dir.exists():
            return rows
        for path in sorted(artifacts_dir.glob("*.json")):
            try:
                rows.append(_load_model(path, WorkbenchArtifact))
            except Exception:
                continue
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows

    def create_artifact(self, payload: WorkbenchArtifactCreateRequest) -> WorkbenchArtifact:
        self.ensure_layout()
        _safe_id(payload.artifact_id, "artifact_id")
        if payload.thread_id is not None:
            self._load_thread(payload.thread_id)
        if self._path("artifacts", payload.artifact_id).exists():
            raise WorkbenchError(f"artifact already exists: {payload.artifact_id}")
        artifact = WorkbenchArtifact(
            artifact_id=payload.artifact_id,
            thread_id=payload.thread_id,
            kind=payload.kind,
            title=payload.title,
            path=payload.path,
            summary=payload.summary,
            notes=payload.notes,
            created_at=_now(),
            updated_at=_now(),
        )
        _atomic_write_json(self._path("artifacts", artifact.artifact_id), artifact.model_dump(mode="json"))
        return artifact

    def list_tools(self) -> list[WorkbenchTool]:
        self.ensure_layout()
        return self._load_list_file(self.root / "tools.json", WorkbenchTool)

    def list_safety_profiles(self) -> list[SafetyProfile]:
        self.ensure_layout()
        return self._load_list_file(self.root / "safety_profiles.json", SafetyProfile)

    def status(self) -> dict[str, Any]:
        self.ensure_layout()
        threads = self.list_threads()
        messages = sum(len(self.list_messages(item["thread_id"])) for item in threads)
        gates = sum(int(item.get("proof_gate_count", 0)) for item in threads)
        return {
            "service": "marius-workbench",
            "status": "online",
            "local_only": True,
            "fake_worker_only": True,
            "real_agent_launch_disabled": True,
            "arbitrary_command_execution_disabled": True,
            "agents": len(self.list_agents()),
            "threads": len(threads),
            "messages": messages,
            "skills": len(self.list_skills()),
            "memories": len(self.list_memories()),
            "artifacts": len(self.list_artifacts()),
            "proof_gates": gates,
            "tools": len(self.list_tools()),
            "safety_profiles": len(self.list_safety_profiles()),
            "workbench_root": str(self.root),
        }


router = APIRouter(prefix="/workbench", tags=["marius-desktop-workbench"])
STORE = WorkbenchStore()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkbenchError):
        detail = str(exc)
        status_code = 404 if "not available" in detail or "does not exist" in detail else 400
        return HTTPException(status_code=status_code, detail=detail)
    raise exc


@router.get("/status")
def get_status() -> dict[str, Any]:
    return STORE.status()


@router.get("/agents", response_model=list[WorkbenchAgent])
def get_agents() -> list[WorkbenchAgent]:
    return STORE.list_agents()


@router.post("/agents", response_model=WorkbenchAgent)
def create_agent(payload: WorkbenchAgentCreateRequest) -> WorkbenchAgent:
    try:
        return STORE.upsert_agent(payload)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/agents/{agent_id}", response_model=WorkbenchAgent)
def get_agent(agent_id: str) -> WorkbenchAgent:
    try:
        return STORE.get_agent(agent_id)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/threads")
def get_threads() -> list[dict[str, Any]]:
    return STORE.list_threads()


@router.post("/threads")
def create_thread(payload: WorkbenchThreadCreateRequest) -> dict[str, Any]:
    try:
        return STORE.create_thread(payload)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str) -> dict[str, Any]:
    try:
        return STORE.get_thread(thread_id)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/threads/{thread_id}/messages")
def get_thread_messages(thread_id: str) -> list[dict[str, Any]]:
    try:
        return STORE.list_messages(thread_id)
    except Exception as exc:
        raise _http_error(exc)


@router.post("/threads/{thread_id}/messages", response_model=WorkbenchMessage)
def post_thread_message(thread_id: str, payload: WorkbenchMessageCreateRequest) -> WorkbenchMessage:
    try:
        return STORE.append_message(thread_id, payload)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/threads/{thread_id}/proof-gates")
def get_thread_proof_gates(thread_id: str) -> list[dict[str, Any]]:
    try:
        return STORE.get_thread(thread_id)["hard_gates"]
    except Exception as exc:
        raise _http_error(exc)


@router.post("/threads/{thread_id}/proof-gates")
def post_thread_proof_gate(thread_id: str, payload: WorkbenchProofGateCreateRequest) -> dict[str, Any]:
    try:
        return STORE.add_proof_gate(thread_id, payload)
    except Exception as exc:
        raise _http_error(exc)


@router.post("/threads/{thread_id}/proof-gates/{gate_id}/decision")
def post_thread_proof_gate_decision(
    thread_id: str,
    gate_id: str,
    payload: WorkbenchProofGateDecisionRequest,
) -> dict[str, Any]:
    try:
        return STORE.decide_proof_gate(thread_id, gate_id, payload)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/skills", response_model=list[WorkbenchSkill])
def get_skills() -> list[WorkbenchSkill]:
    return STORE.list_skills()


@router.post("/skills", response_model=WorkbenchSkill)
def create_skill(payload: WorkbenchSkillCreateRequest) -> WorkbenchSkill:
    try:
        return STORE.create_skill(payload)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/skills/{skill_id}", response_model=WorkbenchSkill)
def get_skill(skill_id: str) -> WorkbenchSkill:
    try:
        return STORE.get_skill(skill_id)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/memories", response_model=list[WorkbenchMemory])
def get_memories() -> list[WorkbenchMemory]:
    return STORE.list_memories()


@router.post("/memories", response_model=WorkbenchMemory)
def create_memory(payload: WorkbenchMemoryCreateRequest) -> WorkbenchMemory:
    try:
        return STORE.create_memory(payload)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/artifacts", response_model=list[WorkbenchArtifact])
def get_artifacts() -> list[WorkbenchArtifact]:
    return STORE.list_artifacts()


@router.post("/artifacts", response_model=WorkbenchArtifact)
def create_artifact(payload: WorkbenchArtifactCreateRequest) -> WorkbenchArtifact:
    try:
        return STORE.create_artifact(payload)
    except Exception as exc:
        raise _http_error(exc)


@router.get("/tools", response_model=list[WorkbenchTool])
def get_tools() -> list[WorkbenchTool]:
    return STORE.list_tools()


@router.get("/safety-profiles", response_model=list[SafetyProfile])
def get_safety_profiles() -> list[SafetyProfile]:
    return STORE.list_safety_profiles()
