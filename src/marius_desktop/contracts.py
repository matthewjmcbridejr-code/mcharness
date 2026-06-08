from datetime import datetime
from typing import List, Literal, Optional, Any, Dict
from pydantic import BaseModel, Field

class MemoryContext(BaseModel):
    task_id: str
    memories: List[str] = Field(default_factory=list)
    source: str
    compacted: bool
    summary: Optional[str] = None

class WorkerResult(BaseModel):
    run_id: str
    task_id: str
    status: Literal["success", "failed", "cancelled", "blocked"]
    summary: str
    artifacts: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    recovery_hint: Optional[str] = None
    raw_output_path: Optional[str] = None

class HumanDecision(BaseModel):
    decision: Literal["approve", "reject", "edit_state"]
    actor: str
    reviewer_note: Optional[str] = None
    state_patch: Dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime

class TaskState(BaseModel):
    task_id: str
    title: str
    description: str
    status: Literal["queued", "running", "paused", "completed", "failed", "cancelled"]
    risk_level: Literal["low", "medium", "high"]
    proof_status: Literal["not_required", "pending", "needs_review", "approved", "rejected", "failed"]
    current_step: str
    agent_id: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    memory_context: Optional[MemoryContext] = None
    worker_run_id: Optional[str] = None
    worker_result: Optional[WorkerResult] = None
    human_decision: Optional[HumanDecision] = None
    recovery_hint: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class WorkerRun(BaseModel):
    run_id: str
    task_id: str
    agent_id: str
    command: str
    args: List[str] = Field(default_factory=list)
    status: Literal["queued", "running", "success", "failed", "cancelled", "blocked"]
    exit_code: Optional[int] = None
    logs_path: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

class ProofReview(BaseModel):
    task_id: str
    step: str
    status: Literal["pending", "approved", "rejected", "failed"]
    decision: Optional[str] = None
    reviewer_note: Optional[str] = None
    decided_at: Optional[datetime] = None

class ToolResult(BaseModel):
    tool_name: str
    status: Literal["success", "failed", "unavailable", "blocked"]
    summary: str
    artifacts: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    recovery_hint: Optional[str] = None

class CapabilityStatus(BaseModel):
    name: str
    status: Literal["available", "unavailable", "disabled", "not_implemented"]
    summary: str
    recovery_hint: Optional[str] = None


class PromptQueueItem(BaseModel):
    prompt_id: str
    title: str
    prompt_path: Optional[str] = None
    status: Literal["queued", "running", "blocked", "done"] = "queued"
    commit_message: Optional[str] = None
    notes: Optional[str] = None


class MinionTask(BaseModel):
    minion_id: str
    role: Optional[str] = None
    scope: str
    status: Literal["queued", "running", "blocked", "done"] = "queued"
    files: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class EvidenceRecord(BaseModel):
    evidence_id: str
    kind: Optional[str] = None
    summary: str
    status: Optional[str] = None
    command_text: Optional[str] = None
    details: Optional[str] = None
    captured_by: str
    artifacts: List[str] = Field(default_factory=list)
    captured_at: datetime


class ScopedCommitPlan(BaseModel):
    commit_message: str
    files: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class HardGate(BaseModel):
    gate_id: str
    kind: str
    reason: str
    triggered_by: str
    blocked: bool = True
    decision: Optional[Literal["approve", "reject", "edit_state"]] = None
    decision_actor: Optional[str] = None
    decision_note: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime


class CaptainTemplate(BaseModel):
    template_id: str
    title: str
    objective: str
    prompt_queue: List[PromptQueueItem] = Field(default_factory=list)
    minion_tasks: List[MinionTask] = Field(default_factory=list)
    hard_gates: List[HardGate] = Field(default_factory=list)
    scoped_commit_plan: Optional[ScopedCommitPlan] = None
    planned_acceptance_commands: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class CaptainRun(BaseModel):
    run_id: str
    objective: str
    status: Literal["active", "blocked", "completed"] = "active"
    prompt_queue: List[PromptQueueItem] = Field(default_factory=list)
    minion_tasks: List[MinionTask] = Field(default_factory=list)
    evidence_records: List[EvidenceRecord] = Field(default_factory=list)
    hard_gates: List[HardGate] = Field(default_factory=list)
    scoped_commit_plan: Optional[ScopedCommitPlan] = None
    next_action: str
    planned_acceptance_commands: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
