from pathlib import Path
from typing import List, Literal, Optional, Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .captain import router as captain_router
from .contracts import CapabilityStatus, TaskState, WorkerRun
from .graph import (
    CHECKPOINT_DB_PATH,
    LANGGRAPH_AVAILABLE,
    McTableTaskGraph,
    TASKS_DIR,
    get_task_path,
    checkpoint_file_exists,
    get_runtime_capabilities,
)
from .worker import WorkerStub, ALLOWED_COMMANDS

router = APIRouter(prefix="/api/marius", tags=["marius-desktop"])
router.include_router(captain_router)

legacy_router = APIRouter(tags=["marius-desktop-legacy"])

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
        "mctable_root": str(Path("_mctable").resolve())
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

@router.post("/tasks", response_model=TaskState)
def create_task(req: TaskCreateRequest):
    if req.command not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Command '{req.command}' is not allowlisted.")

    # Check if task already exists
    try:
        if get_task_path(req.task_id).exists():
            raise HTTPException(status_code=400, detail=f"Task already exists.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id")
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
        raise HTTPException(status_code=404, detail="Task not found.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id")

@router.get("/tasks/{task_id}/events")
def get_task_events(task_id: str):
    graph = McTableTaskGraph()
    try:
        state = graph.load_state(task_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id")

    # Return a simple list of events based on the task state
    return [
        {"event": "task_created", "timestamp": state.created_at.isoformat()},
        {"event": "step_executed", "step": state.current_step, "timestamp": state.updated_at.isoformat()}
    ]

@router.post("/tasks/{task_id}/decision", response_model=TaskState)
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

@router.post("/worker-runs/{run_id}/cancel")
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


@legacy_router.post("/api/mctable/local/dispatch-launch")
def disabled_legacy_launch_route():
    raise HTTPException(status_code=400, detail="deprecated/disabled legacy launch route")
