"""Safe Agent Registry — bounded CLI/remote agent profiles for McHarness."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

BUILTIN_CODEX_ID = "codex_cli"

AgentKind = Literal["cli", "remote"]
AgentAdapter = Literal["codex_cli", "jules_remote", "agy_cli", "custom_cli", "custom_remote"]
AgentStatus = Literal["ready", "not_configured", "disabled", "unsupported", "error"]

SECRET_FIELD_NAMES = frozenset(
    {
        "api_key",
        "secret",
        "token",
        "password",
        "credential",
        "private_key",
        "openrouter_api_key",
    }
)

REGISTERABLE_ADAPTERS = frozenset({"jules_remote"})
DISABLED_TEMPLATE_ADAPTERS = frozenset({"agy_cli", "custom_cli", "custom_remote"})

_FILE_LOCK = threading.Lock()


class McHarnessAgentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: AgentKind
    adapter: AgentAdapter
    description: str = Field(default="", max_length=2000)
    capabilities: list[str] = Field(default_factory=list)
    default_repo_id: str | None = None
    enabled: bool = True


class McHarnessAgentPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] | None = None
    default_repo_id: str | None = None
    enabled: bool | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def agents_registry_path(root: Path) -> Path:
    return root / "agents" / "agents.json"


def agent_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": "codex_cli",
            "label": "Codex CLI",
            "kind": "cli",
            "adapter": "codex_cli",
            "registerable": False,
            "runnable": True,
            "builtin": True,
            "description": "OpenAI Codex CLI via the existing private tmux runner.",
        },
        {
            "id": "jules_remote",
            "label": "Jules Remote",
            "kind": "remote",
            "adapter": "jules_remote",
            "registerable": True,
            "runnable": False,
            "builtin": False,
            "description": "Jules remote worker profile for planning and status only in this version.",
        },
        {
            "id": "agy_cli",
            "label": "AGY CLI Coming Later",
            "kind": "cli",
            "adapter": "agy_cli",
            "registerable": False,
            "runnable": False,
            "builtin": False,
            "description": "Planned AGY / Antigravity CLI adapter. Not available yet.",
        },
        {
            "id": "custom_cli",
            "label": "Custom CLI Coming Later",
            "kind": "cli",
            "adapter": "custom_cli",
            "registerable": False,
            "runnable": False,
            "builtin": False,
            "description": "Custom CLI adapters are disabled to prevent arbitrary shell execution.",
        },
        {
            "id": "custom_remote",
            "label": "Custom Remote Coming Later",
            "kind": "remote",
            "adapter": "custom_remote",
            "registerable": False,
            "runnable": False,
            "builtin": False,
            "description": "Custom remote adapters are disabled in this version.",
        },
    ]


def _ensure_registry_dir(root: Path) -> None:
    agents_registry_path(root).parent.mkdir(parents=True, exist_ok=True)


def _load_registry_document(root: Path) -> dict[str, Any]:
    path = agents_registry_path(root)
    if not path.exists():
        return {"version": 1, "agents": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent registry file is unreadable.") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Agent registry file has invalid shape.")
    agents = data.get("agents")
    if not isinstance(agents, list):
        raise HTTPException(status_code=500, detail="Agent registry file has invalid agents list.")
    return data


def _save_registry_document(root: Path, document: dict[str, Any]) -> None:
    _ensure_registry_dir(root)
    path = agents_registry_path(root)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def load_registered_agents(root: Path) -> list[dict[str, Any]]:
    with _FILE_LOCK:
        document = _load_registry_document(root)
        agents = document.get("agents") or []
        return [dict(item) for item in agents if isinstance(item, dict)]


def _save_registered_agents(root: Path, agents: list[dict[str, Any]]) -> None:
    with _FILE_LOCK:
        document = _load_registry_document(root)
        document["agents"] = agents
        document["updated_at"] = _now_iso()
        _save_registry_document(root, document)


def sanitize_agent_profile(agent: dict[str, Any]) -> dict[str, Any]:
    """Return a safe public view of an agent profile with no secret fields."""
    clean: dict[str, Any] = {}
    for key, value in agent.items():
        lowered = key.lower()
        if lowered in SECRET_FIELD_NAMES or "secret" in lowered or "api_key" in lowered:
            continue
        clean[key] = value
    return clean


def _codex_capabilities() -> list[str]:
    return ["live_terminal", "code_editing", "tests", "read_only_inspection"]


def build_builtin_codex_profile(
    *,
    codex_runner_ready: bool,
    private_only: bool,
) -> dict[str, Any]:
    now = _now_iso()
    status: AgentStatus = "ready" if codex_runner_ready else "disabled"
    return {
        "id": BUILTIN_CODEX_ID,
        "name": "Codex CLI",
        "kind": "cli",
        "adapter": "codex_cli",
        "enabled": True,
        "private_only": private_only,
        "builtin": True,
        "user_created": False,
        "description": "OpenAI Codex CLI for code generation and edits via the private tmux runner.",
        "capabilities": _codex_capabilities(),
        "default_repo_id": None,
        "created_at": now,
        "updated_at": now,
        "status": status,
        "runnable": codex_runner_ready,
        "lane_id": BUILTIN_CODEX_ID,
    }


def _jules_default_capabilities() -> list[str]:
    return ["remote_planning", "status_tracking"]


def _status_for_registered(agent: dict[str, Any], *, codex_runner_ready: bool) -> AgentStatus:
    adapter = str(agent.get("adapter") or "")
    enabled = bool(agent.get("enabled", True))
    if adapter in DISABLED_TEMPLATE_ADAPTERS:
        return "unsupported"
    if adapter == "codex_cli":
        return "ready" if codex_runner_ready and enabled else "disabled"
    if adapter == "jules_remote":
        return "not_configured" if enabled else "disabled"
    return "unsupported"


def _runnable_for_agent(agent: dict[str, Any], *, codex_runner_ready: bool) -> bool:
    if not bool(agent.get("enabled", True)):
        return False
    adapter = str(agent.get("adapter") or "")
    status = _status_for_registered(agent, codex_runner_ready=codex_runner_ready) if not agent.get("builtin") else (
        "ready" if codex_runner_ready else "disabled"
    )
    if adapter == "codex_cli":
        return codex_runner_ready and status == "ready"
    return False


def enrich_agent_profile(agent: dict[str, Any], *, codex_runner_ready: bool) -> dict[str, Any]:
    enriched = sanitize_agent_profile(dict(agent))
    if enriched.get("builtin"):
        enriched["status"] = "ready" if codex_runner_ready else "disabled"
        enriched["runnable"] = codex_runner_ready
        enriched["lane_id"] = BUILTIN_CODEX_ID
    else:
        enriched["status"] = _status_for_registered(enriched, codex_runner_ready=codex_runner_ready)
        enriched["runnable"] = _runnable_for_agent(enriched, codex_runner_ready=codex_runner_ready)
        adapter = str(enriched.get("adapter") or "")
        enriched["lane_id"] = BUILTIN_CODEX_ID if adapter == "codex_cli" else None
    return enriched


def list_all_agents(root: Path, *, codex_runner_ready: bool, private_only: bool) -> list[dict[str, Any]]:
    builtin = build_builtin_codex_profile(codex_runner_ready=codex_runner_ready, private_only=private_only)
    registered = [
        enrich_agent_profile(item, codex_runner_ready=codex_runner_ready)
        for item in load_registered_agents(root)
    ]
    return [builtin, *registered]


def get_agent_by_id(root: Path, agent_id: str, *, codex_runner_ready: bool, private_only: bool) -> dict[str, Any] | None:
    for agent in list_all_agents(root, codex_runner_ready=codex_runner_ready, private_only=private_only):
        if agent.get("id") == agent_id:
            return agent
    return None


def validate_create_request(payload: McHarnessAgentCreateRequest) -> None:
    if payload.adapter == BUILTIN_CODEX_ID or payload.adapter == "codex_cli":
        raise HTTPException(status_code=400, detail="Codex CLI is built-in and cannot be registered again.")
    if payload.adapter in DISABLED_TEMPLATE_ADAPTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Adapter '{payload.adapter}' is not available for registration in this version.",
        )
    if payload.adapter not in REGISTERABLE_ADAPTERS:
        raise HTTPException(status_code=400, detail=f"Adapter '{payload.adapter}' is not supported for registration.")
    template = next((item for item in agent_templates() if item["adapter"] == payload.adapter), None)
    if template is None:
        raise HTTPException(status_code=400, detail=f"Unknown adapter: {payload.adapter}")
    if payload.kind != template["kind"]:
        raise HTTPException(status_code=400, detail=f"Adapter '{payload.adapter}' must use kind '{template['kind']}'.")


def create_registered_agent(root: Path, payload: McHarnessAgentCreateRequest) -> dict[str, Any]:
    validate_create_request(payload)
    now = _now_iso()
    agent_id = f"{payload.adapter}_{uuid.uuid4().hex[:8]}"
    profile: dict[str, Any] = {
        "id": agent_id,
        "name": payload.name.strip(),
        "kind": payload.kind,
        "adapter": payload.adapter,
        "enabled": payload.enabled,
        "private_only": True,
        "builtin": False,
        "user_created": True,
        "description": (payload.description or "").strip(),
        "capabilities": list(payload.capabilities or _jules_default_capabilities() if payload.adapter == "jules_remote" else []),
        "default_repo_id": payload.default_repo_id,
        "created_at": now,
        "updated_at": now,
    }
    agents = load_registered_agents(root)
    agents.append(profile)
    _save_registered_agents(root, agents)
    return enrich_agent_profile(profile, codex_runner_ready=False)


def update_registered_agent(root: Path, agent_id: str, payload: McHarnessAgentPatchRequest) -> dict[str, Any]:
    if agent_id == BUILTIN_CODEX_ID:
        raise HTTPException(status_code=400, detail="Built-in Codex profile metadata cannot be changed through the registry.")
    agents = load_registered_agents(root)
    index = next((idx for idx, item in enumerate(agents) if item.get("id") == agent_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    agent = dict(agents[index])
    if payload.name is not None:
        agent["name"] = payload.name.strip()
    if payload.description is not None:
        agent["description"] = payload.description.strip()
    if payload.capabilities is not None:
        agent["capabilities"] = list(payload.capabilities)
    if payload.default_repo_id is not None:
        agent["default_repo_id"] = payload.default_repo_id or None
    if payload.enabled is not None:
        agent["enabled"] = payload.enabled
    agent["updated_at"] = _now_iso()
    agents[index] = agent
    _save_registered_agents(root, agents)
    return enrich_agent_profile(agent, codex_runner_ready=False)


def delete_registered_agent(root: Path, agent_id: str) -> dict[str, Any]:
    if agent_id == BUILTIN_CODEX_ID:
        raise HTTPException(status_code=400, detail="Built-in Codex profile cannot be deleted.")
    agents = load_registered_agents(root)
    remaining = [item for item in agents if item.get("id") != agent_id]
    if len(remaining) == len(agents):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    _save_registered_agents(root, remaining)
    return {"ok": True, "deleted_id": agent_id}


def agent_status_payload(
    agent: dict[str, Any],
    *,
    codex_runner_ready: bool,
    probe_codex: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    enriched = enrich_agent_profile(agent, codex_runner_ready=codex_runner_ready)
    payload: dict[str, Any] = {
        "id": enriched["id"],
        "name": enriched["name"],
        "adapter": enriched["adapter"],
        "status": enriched["status"],
        "runnable": enriched["runnable"],
        "enabled": enriched.get("enabled", True),
        "notes": [],
    }
    adapter = str(enriched.get("adapter") or "")
    if adapter == "codex_cli" and probe_codex is not None:
        probe = probe_codex()
        payload["probe"] = probe
        if probe.get("installed"):
            payload["notes"].append("Codex executable detected.")
        else:
            payload["notes"].append("Codex executable not detected on host.")
    elif adapter == "jules_remote":
        payload["notes"].append("Jules Remote is registered for planning/status only. Execution support comes next.")
    return sanitize_agent_profile(payload)


def probe_agent(
    agent: dict[str, Any],
    *,
    codex_runner_ready: bool,
    probe_codex: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    adapter = str(agent.get("adapter") or "")
    if adapter == "codex_cli":
        if probe_codex is None:
            raise HTTPException(status_code=503, detail="Codex probe is unavailable.")
        probe = probe_codex()
        return {
            "id": agent.get("id"),
            "adapter": adapter,
            "status": "ready" if probe.get("installed") and codex_runner_ready else "disabled",
            "probe": probe,
            "notes": ["Probe checks executable presence only. No run was started."],
        }
    if adapter == "jules_remote":
        return {
            "id": agent.get("id"),
            "adapter": adapter,
            "status": "not_configured",
            "notes": ["Jules API key support is not available in this version."],
        }
    raise HTTPException(status_code=400, detail=f"Probe is not supported for adapter '{adapter}'.")