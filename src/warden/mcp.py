from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .contracts import TaskState, WorkerRun
from .graph import McTableTaskGraph, checkpoint_file_exists, get_runtime_capabilities
from .worker import ALLOWED_COMMANDS, WorkerStub

FAKE_WORKER_COMMANDS = {
    "fake-worker-success",
    "fake-worker-fail",
    "fake-worker-sleep",
}

MCP_SCHEMA = "warden.mcp.v1"

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - exercised only when MCP is absent
    FastMCP = None  # type: ignore[assignment]


class TaskCreateRequest(BaseModel):
    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)


class TaskResumeRequest(BaseModel):
    task_id: str = Field(min_length=1)
    decision: Literal["approve", "reject", "edit_state"]
    actor: str = Field(min_length=1)
    reviewer_note: Optional[str] = None
    state_patch: dict[str, Any] = Field(default_factory=dict)


def _envelope(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"schema": MCP_SCHEMA, "tool": tool_name, "ok": True, "data": data}


def _task_to_payload(state: TaskState) -> dict[str, Any]:
    return state.model_dump(mode="json")


def _run_to_payload(run: WorkerRun) -> dict[str, Any]:
    return run.model_dump(mode="json")


def _capabilities_payload() -> dict[str, Any]:
    return _envelope(
        "mctable_capabilities",
        {
            "local_only": True,
            "transport": "stdio" if FastMCP is not None else "local-registry",
            "server_available": FastMCP is not None,
            "backend_allowlist": sorted(ALLOWED_COMMANDS),
            "mcp_command_subset": sorted(FAKE_WORKER_COMMANDS),
            "tools": [
                "mctable_task_create",
                "mctable_task_get",
                "mctable_task_resume",
                "mctable_worker_status",
                "mctable_worker_logs",
                "mctable_capabilities",
            ],
            "checkpoint_exists": checkpoint_file_exists(),
            "capabilities": [cap.model_dump(mode="json") for cap in get_runtime_capabilities()]
            + [
                {
                    "name": "mcp",
                    "status": "available" if FastMCP is not None else "disabled",
                    "summary": "Local MCP tool layer is available via stdio when FastMCP is installed.",
                    "recovery_hint": None if FastMCP is not None else "Install mcp to enable stdio transport.",
                }
            ],
        },
    )


def _validate_task_command(command: str) -> None:
    if command not in ALLOWED_COMMANDS:
        raise ValueError(f"Command '{command}' is not allowlisted.")
    if command not in FAKE_WORKER_COMMANDS:
        raise ValueError("MCP only allows fake-worker commands.")


@dataclass
class MariusDesktopMCPRegistry:
    """Local callable MCP registry used for stdio or fallback operation."""

    def mctable_capabilities(self) -> dict[str, Any]:
        return _capabilities_payload()

    def mctable_task_create(
        self,
        task_id: str,
        title: str,
        description: str = "",
        command: str = "fake-worker-success",
        args: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        payload = TaskCreateRequest.model_validate(
            {
                "task_id": task_id,
                "title": title,
                "description": description,
                "command": command,
                "args": args or [],
            }
        )
        _validate_task_command(payload.command)

        graph = McTableTaskGraph()
        graph.create_task(
            task_id=payload.task_id,
            title=payload.title,
            description=payload.description,
            command=payload.command,
            args=payload.args,
        )
        state = graph.drive_task_to_review(payload.task_id)
        return _envelope("mctable_task_create", _task_to_payload(state))

    def mctable_task_get(self, task_id: str) -> dict[str, Any]:
        state = McTableTaskGraph().load_state(task_id)
        return _envelope("mctable_task_get", _task_to_payload(state))

    def mctable_task_resume(
        self,
        task_id: str,
        decision: Literal["approve", "reject", "edit_state"],
        actor: str,
        reviewer_note: Optional[str] = None,
        state_patch: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = TaskResumeRequest.model_validate(
            {
                "task_id": task_id,
                "decision": decision,
                "actor": actor,
                "reviewer_note": reviewer_note,
                "state_patch": state_patch or {},
            }
        )

        state = McTableTaskGraph().resume_task(
            task_id=payload.task_id,
            decision=payload.decision,
            actor=payload.actor,
            reviewer_note=payload.reviewer_note,
            state_patch=payload.state_patch,
        )
        return _envelope("mctable_task_resume", _task_to_payload(state))

    def mctable_worker_status(self, run_id: str) -> dict[str, Any]:
        run = WorkerStub.get_status(run_id)
        return _envelope("mctable_worker_status", _run_to_payload(run))

    def mctable_worker_logs(self, run_id: str) -> dict[str, Any]:
        logs = "".join(list(WorkerStub.stream_logs(run_id)))
        return _envelope("mctable_worker_logs", {"run_id": run_id, "logs": logs})


def create_mcp_server() -> Any:
    if FastMCP is None:
        return None

    registry = MariusDesktopMCPRegistry()
    app = FastMCP(
        "marius-desktop-mcp",
        instructions=(
            "Local-only McHarness MCP tools. "
            "Use stdio transport only and keep all operations scoped to the local worker/task files."
        ),
        host="127.0.0.1",
        stateless_http=False,
    )

    @app.tool()
    def mctable_capabilities() -> dict[str, Any]:
        return registry.mctable_capabilities()

    @app.tool()
    def mctable_task_create(
        task_id: str,
        title: str,
        description: str = "",
        command: str = "fake-worker-success",
        args: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return registry.mctable_task_create(task_id, title, description, command, args)

    @app.tool()
    def mctable_task_get(task_id: str) -> dict[str, Any]:
        return registry.mctable_task_get(task_id)

    @app.tool()
    def mctable_task_resume(
        task_id: str,
        decision: Literal["approve", "reject", "edit_state"],
        actor: str,
        reviewer_note: Optional[str] = None,
        state_patch: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return registry.mctable_task_resume(task_id, decision, actor, reviewer_note, state_patch)

    @app.tool()
    def mctable_worker_status(run_id: str) -> dict[str, Any]:
        return registry.mctable_worker_status(run_id)

    @app.tool()
    def mctable_worker_logs(run_id: str) -> dict[str, Any]:
        return registry.mctable_worker_logs(run_id)

    return app


LOCAL_MCP_REGISTRY = MariusDesktopMCPRegistry()
mcp = create_mcp_server()


if __name__ == "__main__" and mcp is not None:
    mcp.run("stdio")
