#!/usr/bin/env python3
import os
import sys
import requests
import argparse
import re
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

# Try to import prompt_toolkit for better REPL experience
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

DEFAULT_PROBE_URLS = [
    "http://127.0.0.1:8126/api/mcharness/marius",
    "http://127.0.0.1:8128/api/mcharness/marius",
    "http://127.0.0.1:8125/api/mcharness/marius",
]

CONFIG_PATH = os.path.expanduser("~/.config/marius/config.json")
HISTORY_PATH = os.path.expanduser("~/.local/share/marius/history.txt")

class ConfigManager:
    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self.config = self.load()

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save()

class ApiClient:
    def __init__(self, api_base: Optional[str] = None):
        self.api_base = api_base.rstrip("/") if api_base else None

    def probe(self, urls: List[str]) -> Optional[str]:
        for url in urls:
            try:
                resp = requests.get(f"{url.rstrip('/')}/health", timeout=1)
                if resp.status_code == 200:
                    return url.rstrip("/")
            except Exception:
                continue
        return None

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        if not self.api_base:
            return None
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        try:
            if method.upper() == "POST":
                resp = requests.post(url, json=data, timeout=10)
            else:
                resp = requests.get(url, params=params, timeout=10)
            
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def get_health(self) -> bool:
        res = self._request("GET", "health")
        return res is not None and res.get("status") == "OK"

    def get_chat(self, message: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "chat", data={"message": message})

    def get_status(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "status")

    def get_projects(self) -> Optional[List[Dict[str, Any]]]:
        return self._request("GET", "projects")

    def save_memory(self, content: str, category: str = "general") -> Optional[Dict[str, Any]]:
        return self._request("POST", "memory/remember", data={"content": content, "category": category})

    def search_memory(self, query: str) -> Optional[List[Dict[str, Any]]]:
        return self._request("GET", "memory/recall", params={"q": query})

    def get_whereleftoff(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "whereleftoff")

    def get_handoff(self, target: str, context: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "handoff/agent-prompt", data={"target": target, "context": context})

def parse_command(line: str) -> Tuple[Optional[str], List[str]]:
    # Natural language triggers
    if line.lower().startswith(("remember that ", "note that ", "save this ")):
        trigger_len = len(line.split(maxsplit=2)[:2][0]) + len(line.split(maxsplit=2)[:2][1]) + 2
        content = line[trigger_len:].strip()
        return "remember", ["general", content]

    if not line.startswith("/"):
        return None, [line]
    
    parts = line.split(maxsplit=1)
    raw_cmd = parts[0][1:].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    # Aliases
    aliases = {
        "h": "help",
        "s": "status",
        "p": "projects",
        "lo": "leftoff",
        "r": "recall",
        "m": "model",
        "q": "exit",
        "quit": "exit"
    }
    cmd = aliases.get(raw_cmd, raw_cmd)
    
    if cmd == "remember":
        match = re.match(r"^([^:]+):\s*(.*)$", args)
        if match:
            return cmd, [match.group(1).strip(), match.group(2).strip()]
        return cmd, ["general", args.strip()]
    
    if cmd == "recall":
        return cmd, [args.strip()]

    if cmd == "handoff":
        h_parts = args.split(maxsplit=1)
        if len(h_parts) == 2:
            return cmd, [h_parts[0], h_parts[1]]
        return cmd, [args, ""]

    if cmd == "api":
        return cmd, [args.strip()]
        
    return cmd, [args.strip()]

class MariusCLI:
    def __init__(self, api_base: Optional[str] = None):
        self.config = ConfigManager()
        self.client = ApiClient(api_base)
        self.session_stats = {
            "started_at": datetime.now(),
            "messages_sent": 0,
            "memory_writes": 0,
            "last_command": None
        }

    def handle_chat(self, message: str):
        self.session_stats["messages_sent"] += 1
        result = self.client.get_chat(message)
        if result:
            response = result.get("response", "No response.")
            provider = result.get("provider", "unknown")
            model = result.get("model", "")
            
            print(f"\nmarius> {response}")
            footer = f"provider: {provider}"
            if model:
                footer += f" | model: {model}"
            print(f"[{footer}]\n")
        else:
            print("\nError: Could not get chat response. API might be offline.\n")

    def handle_status(self):
        result = self.client.get_status()
        if result:
            print("\n--- System Status ---")
            print(f"Git: {result.get('git', 'N/A')}")
            print(f"Load: {result.get('load', 'N/A')}")
            print("Services:")
            for svc in result.get("services", []):
                print(f"  - {svc['service']}: {svc['status']}")
            print()
        else:
            print("\nError: API offline.\n")

    def handle_projects(self):
        result = self.client.get_projects()
        if result:
            print("\n--- Project Cards ---")
            for p in result:
                print(f"- {p['name']}: {p['description']}")
            print()
        else:
            print("\nError: API offline.\n")

    def handle_remember(self, category: str, content: str):
        if not content:
            print("Usage: /remember [category:] <note>")
            return
        self.session_stats["memory_writes"] += 1
        result = self.client.save_memory(content, category)
        if result:
            print(f"Memory saved under '{category}'.\n")
        else:
            print("\nError: API offline.\n")

    def handle_recall(self, query: str):
        if not query:
            print("Usage: /recall <query>")
            return
        result = self.client.search_memory(query)
        if result:
            print(f"\n--- Recall Results for '{query}' ---")
            for r in result:
                print(f"- [{r['category']}] {r['content']} ({r['created_at']})")
            if not result:
                print("No matches found.")
            print()
        else:
            print("\nError: API offline.\n")

    def handle_leftoff(self):
        result = self.client.get_whereleftoff()
        if result:
            print("\n--- Where You Left Off ---")
            print(result.get("summary", "No recent progress recorded."))
            print("\nRecent Notes:")
            for note in result.get("recent_notes", []):
                print(f"- {note['date']}: {note['content'].strip()}")
            print()
        else:
            print("\nError: API offline.\n")

    def handle_handoff(self, target: str, context: str):
        if not target:
            print("Usage: /handoff <target> [context]")
            return
        result = self.client.get_handoff(target, context)
        if result:
            print(f"\n{result.get('prompt', 'No prompt generated.')}\n")
        else:
            print("\nError: API offline.\n")

    def handle_model(self):
        result = self.client.get_status()
        if result and "model_backend" in result:
            diag = result["model_backend"]
            print("\n--- Model Backend Status ---")
            print(f"Provider: {diag.get('active_provider', 'unknown')}")
            print(f"Ollama Reachable: {'Yes' if diag.get('ollama_reachable') else 'No'}")
            print(f"Ollama URL: {diag.get('ollama_url', 'N/A')}")
            print(f"Configured Model: {diag.get('configured_model', 'N/A')}")
            models = diag.get("available_models", [])
            if models:
                print(f"Available Models: {', '.join(models)}")
            print()
        else:
            print("\nModel Status: Unknown (API offline)\n")

    def handle_api(self, url: str):
        if not url:
            print(f"Current API Base: {self.client.api_base}")
            return
        self.client.api_base = url.rstrip("/")
        self.config.set("api_base", self.client.api_base)
        if self.client.get_health():
            print(f"API Base updated to {self.client.api_base} (Online)")
        else:
            print(f"API Base updated to {self.client.api_base} (Warning: Offline)")

    def handle_config(self):
        print("\n--- Configuration ---")
        print(f"Config Path: {self.config.path}")
        print(f"API Base: {self.client.api_base}")
        print(f"History Path: {HISTORY_PATH}")
        print()

    def handle_session(self):
        print("\n--- Session Notes ---")
        print(f"API Base: {self.client.api_base}")
        
        status = self.client.get_status()
        if status and "model_backend" in status:
            diag = status["model_backend"]
            print(f"Provider: {diag.get('active_provider')}")
            print(f"Model: {diag.get('configured_model')}")
        else:
            print("Provider/Model: Unknown")

        print(f"Started At: {self.session_stats['started_at'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Messages Sent: {self.session_stats['messages_sent']}")
        print(f"Memory Writes: {self.session_stats['memory_writes']}")
        print(f"Last Command: {self.session_stats['last_command']}")
        print()

    def run_command(self, line: str) -> bool:
        self.session_stats["last_command"] = line
        cmd, args = parse_command(line)
        if cmd is None:
            self.handle_chat(args[0])
            return True
            
        if cmd == "exit":
            return False
        elif cmd == "help":
            print("\nMarius Commands:")
            print("  /status (/s)        - Server & Project health")
            print("  /projects (/p)      - List active project cards")
            print("  /leftoff (/lo)      - Get last recorded progress")
            print("  /remember <note>    - Save a durable fact")
            print("  /recall (/r) <q>    - Search memory")
            print("  /handoff <target>   - Generate handoff prompt")
            print("  /model (/m)         - Show current model info")
            print("  /api [url]          - View or set API base URL")
            print("  /config             - View current configuration")
            print("  /session            - View session statistics")
            print("  /clear              - Clear terminal")
            print("  /help (/h)          - Show this help")
            print("  /exit (/q)          - Quit\n")
        elif cmd == "status":
            self.handle_status()
        elif cmd == "projects":
            self.handle_projects()
        elif cmd == "leftoff":
            self.handle_leftoff()
        elif cmd == "remember":
            self.handle_remember(args[0], args[1])
        elif cmd == "recall":
            self.handle_recall(args[0])
        elif cmd == "handoff":
            self.handle_handoff(args[0], args[1])
        elif cmd == "model":
            self.handle_model()
        elif cmd == "api":
            self.handle_api(args[0])
        elif cmd == "config":
            self.handle_config()
        elif cmd == "session":
            self.handle_session()
        elif cmd == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
        else:
            print(f"Unknown command: /{cmd}. Type /help for available commands.")
        return True

    def show_banner(self):
        print("Marius Resident Agent")
        if self.client.get_health():
            print("McServer: online")
            status = self.client.get_status()
            if status and "model_backend" in status:
                diag = status["model_backend"]
                provider = diag.get("active_provider")
                model = diag.get("configured_model")
                print(f"Model: {provider} / {model}")
                if provider == "fallback":
                    print("Warning: Operating in fallback mode (Ollama offline)")
            print("Memory: ready")
        else:
            print("McServer: offline")
            print("Marius API is offline.")
            print("Start the Warden dev server, then run ./scripts/marius again.")
            sys.exit(0)
        print("Type /help for commands. Ctrl+C or /exit to quit.\n")

    def repl(self):
        self.show_banner()
        
        session = None
        if HAS_PROMPT_TOOLKIT:
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            session = PromptSession(history=FileHistory(HISTORY_PATH))

        while True:
            try:
                if session:
                    line = session.prompt("you> ").strip()
                else:
                    line = input("you> ").strip()
                
                if not line:
                    continue
                
                if not self.run_command(line):
                    break
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Marius CLI Chat Client")
    parser.add_argument("--once", type=str, help="Run a single chat message and exit")
    parser.add_argument("--api", type=str, help="Marius API base URL")
    args = parser.parse_args()

    config = ConfigManager()
    
    # API Resolution Order
    api_base = args.api
    if not api_base:
        api_base = os.getenv("MARIUS_API_BASE")
    if not api_base:
        api_base = config.get("api_base")
    
    client = ApiClient(api_base)
    
    if not api_base:
        # Auto-probe
        api_base = client.probe(DEFAULT_PROBE_URLS)
        if api_base:
            client.api_base = api_base
            config.set("api_base", api_base)
    
    if args.once:
        if not client.get_health():
            print("Marius API is offline.")
            sys.exit(1)
        cli = MariusCLI(client.api_base)
        cli.run_command(args.once)
    else:
        cli = MariusCLI(client.api_base)
        cli.repl()
