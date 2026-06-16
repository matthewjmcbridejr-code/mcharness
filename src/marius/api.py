from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from .projects import get_projects, ProjectCard
from .memory import save_fact, recall_facts, get_where_left_off, set_where_left_off, get_recent_summaries
from .tools import get_system_status
from .router import chat_completion, create_handoff_prompt

router = APIRouter(prefix="/api/mcharness/marius", tags=["marius-core"])

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None

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
    return get_system_status()

@router.post("/chat")
def chat(req: ChatRequest):
    response, provider = chat_completion(req.message, req.model)
    return {"response": response, "provider": provider}

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
