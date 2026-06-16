import requests
import json
import os
from typing import Tuple, Optional, Dict, Any, List

def get_ollama_urls() -> Tuple[str, str, str]:
    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    return base_url, f"{base_url}/api/chat", f"{base_url}/api/tags"

def chat_completion(prompt: str, model: Optional[str] = None) -> Tuple[str, str, str]:
    base_url, chat_url, _ = get_ollama_urls()
    target_model = model or os.getenv("MARIUS_OLLAMA_MODEL", "llama3.2:3b")
    timeout = int(os.getenv("MARIUS_OLLAMA_TIMEOUT", "10"))
    try:
        response = requests.post(
            chat_url,
            json={
                "model": target_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            },
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            content = data.get("message", {}).get("content", "")
            return content, "ollama", target_model
    except Exception:
        pass
    
    return ("Ollama is currently unavailable. I am operating in safe-mode with limited intelligence. "
            "I can still help with memory and status tasks."), "fallback", ""

def get_ollama_diagnostics() -> Dict[str, Any]:
    base_url, _, tags_url = get_ollama_urls()
    reachable = False
    available_models = []
    configured_model = os.getenv("MARIUS_OLLAMA_MODEL", "llama3.2:3b")
    try:
        resp = requests.get(tags_url, timeout=2)
        if resp.status_code == 200:
            reachable = True
            available_models = [m.get("name") for m in resp.json().get("models", [])]
    except Exception:
        pass
    
    return {
        "ollama_reachable": reachable,
        "ollama_url": base_url,
        "configured_model": configured_model,
        "available_models": available_models,
        "active_provider": "ollama" if reachable else "fallback"
    }

def create_handoff_prompt(target: str, context: str) -> str:
    prompts = {
        "codex": f"--- CODEX HANDOFF ---\nContext: {context}\n\nTask: Please continue the development based on the above context.",
        "grok": f"--- GROK HANDOFF ---\nContext: {context}\n\nHey Grok, here is where I am. Can you take it from here?",
        "antigravity": f"--- ANTIGRAVITY HANDOFF ---\nContext: {context}\n\nExecute mission with following constraints: {context}",
    }
    return prompts.get(target.lower(), f"--- GENERIC HANDOFF ---\nContext: {context}")
