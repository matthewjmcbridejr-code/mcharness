#!/usr/bin/env python3
import os
import sys
import requests
import argparse
import re
import json
import time
import subprocess
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List, Union

# Try to import prompt_toolkit for better REPL experience
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

DEFAULT_PORT = 6969
DEFAULT_API_BASE = f"http://127.0.0.1:{DEFAULT_PORT}/api/mcharness/marius"

# State Paths
CONFIG_DIR = Path.home() / ".config" / "marius"
STATE_DIR = Path.home() / ".local" / "state" / "marius"
SHARE_DIR = Path.home() / ".local" / "share" / "marius"

CONFIG_PATH = CONFIG_DIR / "config.json"
PID_PATH = STATE_DIR / "marius.pid"
LOG_PATH = STATE_DIR / "marius.log"
HISTORY_PATH = SHARE_DIR / "history.txt"

class ConfigManager:
    def __init__(self, path: Union[Path, str] = CONFIG_PATH):
        self.path = Path(path)
        self.config = self.load()

    def load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
                resp = requests.post(url, json=data, timeout=5)
            else:
                resp = requests.get(url, params=params, timeout=5)
            
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
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
        parts = line.split(maxsplit=2)
        if len(parts) > 2:
            content = parts[2]
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
    
    return cmd, [args.strip()]

class MariusCLI:
    def __init__(self, api_base: Optional[str] = None):
        self.config = ConfigManager()
        self.client = ApiClient(api_base)
        self.repo_root = Path(__file__).resolve().parents[1]
        self.session_stats = {
            "started_at": datetime.now(),
            "messages_sent": 0,
            "memory_writes": 0,
            "last_command": None
        }

    def start_server(self):
        if self.client.get_health():
            return True

        print(f"Starting Marius API on port {DEFAULT_PORT}...")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        
        venv_python = self.repo_root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            venv_python = Path(sys.executable)

        cmd = [
            str(venv_python), "-m", "uvicorn", "src.warden.app:app",
            "--host", "127.0.0.1", "--port", str(DEFAULT_PORT),
            "--log-level", "warning"
        ]
        
        log_file = open(LOG_PATH, "a")
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.repo_root),
            stdout=log_file,
            stderr=log_file,
            preexec_fn=os.setsid,
            env={**os.environ, "PYTHONPATH": str(self.repo_root / "src")}
        )
        
        with open(PID_PATH, "w") as f:
            f.write(str(proc.pid))
            
        # Wait for health
        self.client.api_base = DEFAULT_API_BASE
        for _ in range(20):
            if self.client.get_health():
                print("Marius API is online.")
                return True
            time.sleep(0.5)
            
        print(f"Error: Marius API failed to start. Check logs at {LOG_PATH}")
        return False

    def stop_server(self):
        if PID_PATH.exists():
            try:
                with open(PID_PATH, "r") as f:
                    pid = int(f.read().strip())
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                print(f"Stopped Marius API (PID {pid})")
                PID_PATH.unlink()
            except Exception as e:
                print(f"Error stopping server: {e}")
                if PID_PATH.exists(): PID_PATH.unlink()
        else:
            print("No PID file found. Server might not be running via this script.")

    def status_server(self):
        online = self.client.get_health()
        print(f"Marius API: {'Online' if online else 'Offline'}")
        print(f"API Base: {self.client.api_base}")
        
        if PID_PATH.exists():
            with open(PID_PATH, "r") as f:
                print(f"PID: {f.read().strip()}")
        
        if online:
            status = self.client.get_status()
            if status and "model_backend" in status:
                diag = status["model_backend"]
                print(f"Provider: {diag.get('active_provider')}")
                print(f"Model: {diag.get('configured_model')}")

    def doctor(self):
        print("Marius Doctor Diagnostics")
        print("-" * 30)
        print(f"Repo Root: {self.repo_root}")
        venv_python = self.repo_root / ".venv" / "bin" / "python"
        print(f"Venv Python: {'Found' if venv_python.exists() else 'Not Found (using system)'}")
        print(f"Config Path: {CONFIG_PATH} ({'Exists' if CONFIG_PATH.exists() else 'Missing'})")
        print(f"PID File: {PID_PATH} ({'Exists' if PID_PATH.exists() else 'Missing'})")
        
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', DEFAULT_PORT))
        print(f"Port {DEFAULT_PORT}: {'Busy' if result == 0 else 'Free'}")
        sock.close()
        
        print(f"API Base: {self.client.api_base}")
        health = self.client.get_health()
        print(f"Health Check: {'OK' if health else 'FAILED'}")
        
        if health:
            status = self.client.get_status()
            if status and "model_backend" in status:
                diag = status["model_backend"]
                print(f"Ollama Reachable: {'Yes' if diag.get('ollama_reachable') else 'No'}")
        print("-" * 30)

    def tail_logs(self):
        if not LOG_PATH.exists():
            print("No log file found.")
            return
        print(f"Tailing logs at {LOG_PATH} (Ctrl+C to stop)...")
        try:
            subprocess.run(["tail", "-n", "50", "-f", str(LOG_PATH)])
        except KeyboardInterrupt:
            pass

    def handle_chat(self, message: str):
        self.session_stats["messages_sent"] += 1
        result = self.client.get_chat(message)
        if result:
            response = result.get("response", "No response.")
            provider = result.get("provider", "unknown")
            model = result.get("model", "")
            print(f"\nmarius> {response}")
            footer = f"provider: {provider}"
            if model: footer += f" | model: {model}"
            print(f"[{footer}]\n")
        else:
            print("\nError: API offline.\n")

    def run_command(self, line: str) -> bool:
        self.session_stats["last_command"] = line
        cmd, args = parse_command(line)
        if cmd is None:
            self.handle_chat(args[0])
            return True
            
        if cmd == "exit": return False
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
        elif cmd == "status": self.handle_status()
        elif cmd == "projects": self.handle_projects()
        elif cmd == "leftoff": self.handle_leftoff()
        elif cmd == "remember": self.handle_remember(args[0], args[1])
        elif cmd == "recall": self.handle_recall(args[0])
        elif cmd == "model": self.handle_model()
        elif cmd == "api": self.handle_api(args[0])
        elif cmd == "config": self.handle_config()
        elif cmd == "session": self.handle_session()
        elif cmd == "clear": os.system('cls' if os.name == 'nt' else 'clear')
        else: print(f"Unknown command: /{cmd}. Type /help for available commands.")
        return True

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
        else: print("\nError: API offline.\n")

    def handle_projects(self):
        result = self.client.get_projects()
        if result:
            print("\n--- Project Cards ---")
            for p in result: print(f"- {p['name']}: {p['description']}")
            print()
        else: print("\nError: API offline.\n")

    def handle_remember(self, category: str, content: str):
        if not content:
            print("Usage: /remember [category:] <note>")
            return
        self.session_stats["memory_writes"] += 1
        result = self.client.save_memory(content, category)
        if result: print(f"Memory saved under '{category}'.\n")
        else: print("\nError: API offline.\n")

    def handle_recall(self, query: str):
        if not query:
            print("Usage: /recall <query>")
            return
        result = self.client.search_memory(query)
        if result:
            print(f"\n--- Recall Results for '{query}' ---")
            for r in result: print(f"- [{r['category']}] {r['content']} ({r['created_at']})")
            if not result: print("No matches found.")
            print()
        else: print("\nError: API offline.\n")

    def handle_leftoff(self):
        result = self.client.get_whereleftoff()
        if result:
            print("\n--- Where You Left Off ---")
            print(result.get("summary", "No recent progress recorded."))
            print("\nRecent Notes:")
            for note in result.get("recent_notes", []):
                print(f"- {note['date']}: {note['content'].strip()}")
            print()
        else: print("\nError: API offline.\n")

    def handle_model(self):
        result = self.client.get_status()
        if result and "model_backend" in result:
            diag = result["model_backend"]
            print("\n--- Model Backend Status ---")
            print(f"Provider: {diag.get('active_provider', 'unknown')}")
            print(f"Ollama Reachable: {'Yes' if diag.get('ollama_reachable') else 'No'}")
            print(f"Configured Model: {diag.get('configured_model', 'N/A')}")
            print()
        else: print("\nModel Status: Unknown (API offline)\n")

    def handle_api(self, url: str):
        if not url:
            print(f"Current API Base: {self.client.api_base}")
            return
        self.client.api_base = url.rstrip("/")
        self.config.set("api_base", self.client.api_base)
        print(f"API Base updated to {self.client.api_base}")

    def handle_config(self):
        print(f"\nConfig Path: {self.config.path}")
        print(f"API Base: {self.client.api_base}")
        print(f"History: {HISTORY_PATH}\n")

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
        print()

    def repl(self):
        print("Marius Resident Agent")
        if self.client.get_health():
            print("McServer: online")
        else:
            if not self.start_server():
                sys.exit(1)
        
        print("Type /help for commands. Ctrl+C or /exit to quit.\n")
        
        session = None
        if HAS_PROMPT_TOOLKIT:
            SHARE_DIR.mkdir(parents=True, exist_ok=True)
            session = PromptSession(history=FileHistory(str(HISTORY_PATH)))

        while True:
            try:
                line = session.prompt("you> ").strip() if session else input("you> ").strip()
                if not line: continue
                if not self.run_command(line): break
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Marius CLI Launcher")
    parser.add_argument("command", nargs="?", choices=["start", "stop", "restart", "status", "doctor", "logs", "chat"], default="chat")
    parser.add_argument("--once", type=str, help="Run a single chat message and exit")
    parser.add_argument("--api", type=str, help="Marius API base URL")
    args = parser.parse_args()

    config = ConfigManager()
    api_base = args.api or os.getenv("MARIUS_API_BASE") or config.get("api_base") or DEFAULT_API_BASE
    
    cli = MariusCLI(api_base)
    
    if args.once:
        if not cli.client.get_health():
            cli.start_server()
        cli.run_command(args.once)
    elif args.command == "start": cli.start_server()
    elif args.command == "stop": cli.stop_server()
    elif args.command == "restart":
        cli.stop_server()
        cli.start_server()
    elif args.command == "status": cli.status_server()
    elif args.command == "doctor": cli.doctor()
    elif args.command == "logs": cli.tail_logs()
    else: cli.repl()
