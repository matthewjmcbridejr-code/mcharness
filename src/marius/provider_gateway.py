import os
import logging
import httpx
import json
import time
from typing import Dict, Any, List, Optional, AsyncGenerator, Union
from .providers.ollama import OllamaProvider
from .providers.openrouter import OpenRouterProvider
from .providers.groq import GroqProvider
from .providers.gemini import GeminiProvider
from .model_profiles import get_profile, get_system_prompt, DEFAULT_PROFILE, EMBEDDING_MODELS
from .grounding import get_grounding_pack
from .memory import get_where_left_off
from .brain_context import build_brain_context_pack

logger = logging.getLogger(__name__)

class ProviderGateway:
    def __init__(self):
        self.mode = os.getenv("MARIUS_PROVIDER_MODE", "local").lower()
        self.allow_cloud = os.getenv("MARIUS_ALLOW_CLOUD", "0") == "1"
        self.current_profile = os.getenv("MARIUS_MODEL_PROFILE", DEFAULT_PROFILE).lower()
        self.forced_model = os.getenv("MARIUS_OLLAMA_MODEL")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.brain_context_enabled = os.getenv("MARIUS_BRAIN_CONTEXT", "1") == "1"
        self.max_brain_records = int(os.getenv("MARIUS_BRAIN_MAX_RECORDS", "5"))

    async def get_available_ollama_models(self) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{self.ollama_url.rstrip('/')}/api/tags")
                if resp.status_code == 200:
                    return [m.get("name") for m in resp.json().get("models", [])]
        except Exception:
            pass
        return []

    async def resolve_model_and_provider(self) -> tuple:
        """Resolve which model and provider to use based on mode and profile."""
        profile = get_profile(self.current_profile)
        available_ollama = await self.get_available_ollama_models()
        
        # Priority 1: Forced model
        if self.forced_model:
            return "ollama", self.forced_model, profile

        # Priority 2: Resolve from profile models (Local preferred)
        if self.mode in ["local", "auto"]:
            for model in profile["models"]:
                if model in available_ollama or f"{model}:latest" in available_ollama:
                    return "ollama", model, profile

        # Priority 3: Cloud (if enabled and mode is cloud/auto)
        if (self.mode in ["cloud", "auto"]) and self.allow_cloud:
            if self.current_profile == "code":
                if os.getenv("GROQ_API_KEY"):
                    return "groq", os.getenv("GROQ_CODER_MODEL", "qwen-2.5-coder-32b"), profile
                if os.getenv("OPENROUTER_API_KEY"):
                    return "openrouter", os.getenv("OPENROUTER_CODER_MODEL", "qwen/qwen-2.5-coder-32b"), profile
            
            if self.current_profile == "deep":
                if os.getenv("GEMINI_API_KEY"):
                    return "gemini", os.getenv("GEMINI_DEEP_MODEL", "gemini-2.0-flash-thinking-exp"), profile
                if os.getenv("OPENROUTER_API_KEY"):
                    return "openrouter", os.getenv("OPENROUTER_DEEP_MODEL", "meta-llama/llama-3.3-70b-instruct"), profile

            if self.mode == "cloud":
                if os.getenv("GROQ_API_KEY"):
                    return "groq", "llama-3.3-70b-versatile", profile
                if os.getenv("OPENROUTER_API_KEY"):
                    return "openrouter", "meta-llama/llama-3.3-70b-instruct", profile

        # Priority 4: Fallback for local: use the first available model that isn't an embedding model
        if self.mode in ["local", "auto"]:
            for model in available_ollama:
                if model not in EMBEDDING_MODELS and not any(m in model for m in EMBEDDING_MODELS):
                    return "ollama", model, profile

        # Ultimate fallback: llama3.2:3b via Ollama (only if Ollama seems reachable)
        if available_ollama:
            return "ollama", "llama3.2:3b", profile

        return "fallback", "none", profile

    async def chat(self, prompt: str, history: List[Dict[str, str]] = None, workspace: Dict[str, Any] = None) -> Dict[str, Any]:
        from .model_profiles import ROUTER_MODELS, EMBEDDING_MODELS
        
        provider_name, model, profile = await self.resolve_model_and_provider()
        
        auto_switch_msg = None
        # Check if the model is router-only or embedding-only
        if model in ROUTER_MODELS or model in EMBEDDING_MODELS or any(m in model for m in EMBEDDING_MODELS):
            # Auto-switch to best installed chat model
            available = await self.get_available_ollama_models()
            chat_priorities = ['llama3.2:1b', 'gemma3:1b', 'qwen3:0.6b', 'llama3.2:3b']
            target_model = None
            for m in chat_priorities:
                if m in available or f"{m}:latest" in available:
                    target_model = m
                    break
            
            if target_model:
                auto_switch_msg = f"{model} is router-only. Switched chat model to {target_model}."
                model = target_model
                provider_name = "ollama"
            else:
                return {
                    "response": f"Selected model {model} is not suitable for chat and no alternatives were found.",
                    "provider": "fallback",
                    "model": model,
                    "elapsed": 0
                }

        messages = history or []
        # Build systematic grounding context
        if not any(m["role"] == "system" for m in messages):
            # 1. Base system behavior
            system_prompt = get_system_prompt(self.current_profile)
            
            # 2. Grounding pack (Identity, Projects, Anti-hallucination)
            grounding_pack = get_grounding_pack()
            
            # 3. Recent progress / Memory context
            where_left_off = get_where_left_off()
            memory_context = f"\n## Recent Progress\n{where_left_off}\n"
            
            # 4. Workspace context
            ws_context = ""
            if workspace:
                ws_context = f"\n## Current Workspace\nRepo: {workspace.get('repo_path')}\nRunner Enabled: {workspace.get('runner_enabled')}\n"
            
            # 5. Brain Context Retrieval
            brain_pack = None
            brain_context_text = ""
            if self.brain_context_enabled:
                # Use project from workspace if available
                target_project = workspace.get("project") if workspace else None
                brain_pack = build_brain_context_pack(prompt, project=target_project, limit=self.max_brain_records)
                brain_context_text = f"\n## Brain Memory\n{brain_pack['context_text']}\n"
                brain_context_text += "Instruction: Use Brain Memory when relevant. Cite record IDs if used. Do not invent facts outside context.\n"
            
            full_system_msg = f"{system_prompt}\n\n{grounding_pack}\n\n{memory_context}\n{ws_context}\n{brain_context_text}"
            messages.insert(0, {"role": "system", "content": full_system_msg})
        
        messages.append({"role": "user", "content": prompt})

        provider = None
        if provider_name == "ollama":
            provider = OllamaProvider(model, base_url=self.ollama_url, timeout=profile["timeout"])
        elif provider_name == "groq":
            provider = GroqProvider(os.getenv("GROQ_API_KEY"), model, timeout=profile["timeout"])
        elif provider_name == "openrouter":
            provider = OpenRouterProvider(os.getenv("OPENROUTER_API_KEY"), model, timeout=profile["timeout"])
        elif provider_name == "gemini":
            provider = GeminiProvider(os.getenv("GEMINI_API_KEY"), model, timeout=profile["timeout"])

        if provider:
            try:
                start_time = time.time()
                result = await provider.complete(
                    messages, 
                    temperature=profile["temperature"], 
                    max_tokens=profile["max_tokens"]
                )
                elapsed = time.time() - start_time
                
                response_text = result["choices"][0]["message"]["content"]
                return {
                    "response": response_text,
                    "provider": provider_name,
                    "model": model,
                    "elapsed": round(elapsed, 1),
                    "profile": self.current_profile,
                    "warning": auto_switch_msg,
                    "brain_context": {
                        "enabled": self.brain_context_enabled,
                        "record_ids": brain_pack["record_ids"] if brain_pack else []
                    } if self.brain_context_enabled else None
                }
            finally:
                if hasattr(provider, "cleanup"):
                    await provider.cleanup()
        
        return {
            "response": "No suitable provider found or configured.",
            "provider": "fallback",
            "model": "none",
            "elapsed": 0
        }

    async def benchmark(self, models: List[str] = None, quick: bool = True) -> Dict[str, Any]:
        from .benchmark import MariusBenchmark
        available = await self.get_available_ollama_models()
        target_models = models or ["marius-fast", "marius-default", "marius-code-local", "qwen3:0.6b", "gemma3:1b", "llama3.2:1b", "llama3.2:3b", "qwen2.5-coder:3b", "qwen3:4b"]
        
        valid_targets = [m for m in target_models if m in available or f"{m}:latest" in available]
        
        benchmarker = MariusBenchmark(self)
        results = await benchmarker.run_benchmark(valid_targets, quick=quick)
        recommendations = benchmarker.get_recommendations(results)
        
        return {
            "results": results,
            "recommendations": recommendations
        }
