import requests
import json
import os
from typing import Tuple, Optional

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = os.getenv("MARIUS_MODEL", "llama3")

def chat_completion(prompt: str, model: Optional[str] = None) -> Tuple[str, str]:
    target_model = model or DEFAULT_MODEL
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": target_model,
                "prompt": prompt,
                "stream": False
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json().get("response", ""), f"ollama:{target_model}"
    except Exception as e:
        # Log error in a real system
        pass
    
    return ("Ollama is currently unavailable. I am operating in safe-mode with limited intelligence. "
            "I can still help with memory and status tasks."), "fallback"

def create_handoff_prompt(target: str, context: str) -> str:
    prompts = {
        "codex": f"--- CODEX HANDOFF ---\nContext: {context}\n\nTask: Please continue the development based on the above context.",
        "grok": f"--- GROK HANDOFF ---\nContext: {context}\n\nHey Grok, here is where I am. Can you take it from here?",
        "antigravity": f"--- ANTIGRAVITY HANDOFF ---\nContext: {context}\n\nExecute mission with following constraints: {context}",
    }
    return prompts.get(target.lower(), f"--- GENERIC HANDOFF ---\nContext: {context}")
