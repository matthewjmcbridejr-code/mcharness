import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from .projects import get_projects, ProjectCard
from .memory import save_fact, recall_facts, get_where_left_off, set_where_left_off, get_recent_summaries
from .tools import get_system_status
from .router import chat_completion, create_handoff_prompt, get_ollama_diagnostics, test_ollama_model
from .provider_gateway import ProviderGateway
from .model_profiles import MODEL_PROFILES
from .grounding import GroundingPack

router = APIRouter(prefix="/api/mcharness/marius", tags=["marius-core"])
gateway = ProviderGateway()

class WorkspaceContext(BaseModel):
    repo_path: str
    branch: Optional[str] = "unknown"
    dirty: Optional[str] = "unknown"
    runner_enabled: bool

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None
    workspace: Optional[WorkspaceContext] = None

class ProfileRequest(BaseModel):
    profile: str

class ModeRequest(BaseModel):
    mode: str

class ModelRequest(BaseModel):
    model: str

class MemoryRequest(BaseModel):
    content: str
    category: str = "general"

class HandoffRequest(BaseModel):
    target: str
    context: str

@router.get("/health")
def health():
    return {"status": "OK", "service": "marius-core"}

@router.get("/status")
def status():
    # Tools already redacts secrets
    sys_status = get_system_status()
    ollama_diag = get_ollama_diagnostics()
    return {**sys_status, "model_backend": ollama_diag}

@router.get("/model/test")
def model_test():
    return test_ollama_model()

@router.post("/chat")
async def chat(req: ChatRequest):
    if req.model:
        gateway.forced_model = req.model
    
    workspace_dict = req.workspace.model_dump() if req.workspace else None
    result = await gateway.chat(req.message, req.history, workspace_dict)
    return result

@router.get("/providers")
async def get_providers():
    return {
        "current_mode": gateway.mode,
        "allow_cloud": gateway.allow_cloud,
        "providers": [
            {"name": "ollama", "local": True, "configured": True},
            {"name": "groq", "local": False, "configured": bool(os.getenv("GROQ_API_KEY"))},
            {"name": "openrouter", "local": False, "configured": bool(os.getenv("OPENROUTER_API_KEY"))},
            {"name": "gemini", "local": False, "configured": bool(os.getenv("GEMINI_API_KEY"))},
        ]
    }

@router.post("/provider/mode")
async def set_provider_mode(req: ModeRequest):
    if req.mode not in ["local", "cloud", "auto"]:
        raise HTTPException(status_code=400, detail="Invalid mode")
    gateway.mode = req.mode
    return {"status": "ok", "mode": gateway.mode}

@router.get("/models")
async def get_models():
    available_ollama = await gateway.get_available_ollama_models()
    return {
        "current_profile": gateway.current_profile,
        "forced_model": gateway.forced_model,
        "available_ollama": available_ollama,
        "profiles": MODEL_PROFILES
    }

@router.post("/model/set")
async def set_model(req: ModelRequest):
    gateway.forced_model = req.model if req.model != "auto" else None
    return {"status": "ok", "model": gateway.forced_model or "auto"}

@router.post("/model/profile")
async def set_profile(req: ProfileRequest):
    if req.profile not in MODEL_PROFILES:
        raise HTTPException(status_code=400, detail="Invalid profile")
    gateway.current_profile = req.profile
    return {"status": "ok", "profile": gateway.current_profile}

@router.post("/model/bench")
async def run_benchmark(req: Dict[str, Any] = None):
    req = req or {}
    quick = req.get("quick", True)
    return await gateway.benchmark(quick=quick)

@router.get("/model/recommendation")
async def get_recommendation():
    res = await gateway.benchmark(quick=True)
    return res["recommendations"]

@router.get("/model/missing")
async def get_missing_models():
    from .model_profiles import KNOWN_MODELS
    available = await gateway.get_available_ollama_models()
    missing = [m for m in KNOWN_MODELS if m not in available and f"{m}:latest" not in available]
    return {"missing": missing}

@router.get("/context")
async def get_context():
    gp = GroundingPack()
    return {"facts": gp.facts}

@router.post("/context/reload")
async def reload_context():
    return {"status": "ok", "message": "Grounding pack will be reloaded on next request."}

@router.post("/memory/remember")
def remember(req: MemoryRequest):
    save_fact(req.content, req.category)
    # If category is 'progress' or 'status', also update where_left_off
    if req.category.lower() in ["progress", "status", "leftoff"]:
        set_where_left_off(req.content)
    return {"status": "saved"}

@router.get("/memory/recall")
def recall(q: str):
    return recall_facts(q)

@router.get("/projects")
def projects():
    return get_projects()

@router.get("/whereleftoff")
def whereleftoff():
    return {
        "summary": get_where_left_off(),
        "recent_notes": get_recent_summaries()
    }

@router.post("/handoff/agent-prompt")
def handoff(req: HandoffRequest):
    return {"prompt": create_handoff_prompt(req.target, req.context)}

# --- Search / Brain Endpoints ---

class SearchQueryRequest(BaseModel):
    query: str
    project: Optional[str] = None
    limit: int = 5

class SearchExportRequest(BaseModel):
    project: str
    repo_path: str

@router.get("/search/status")
async def get_search_status():
    from .search_provider import get_search_provider
    return get_search_provider().status()

@router.post("/search/export")
async def run_search_export(req: SearchExportRequest):
    from .search_provider import get_search_provider
    return get_search_provider().export(req.project, req.repo_path)

@router.post("/search/query")
async def run_search_query(req: SearchQueryRequest):
    from .search_provider import get_search_provider
    provider = get_search_provider()
    results = provider.search(req.query, req.project, req.limit)
    status = provider.status()
    return {
        "provider": status.get("provider"),
        "query": req.query,
        "project": req.project,
        "results": results
    }
