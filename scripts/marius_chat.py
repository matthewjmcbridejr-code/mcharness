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

DEBUG = os.getenv("MARIUS_DEBUG") == "1"

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG] {msg}", file=sys.stderr)

class ConfigManager:
    def __init__(self, path: Union[Path, str] = CONFIG_PATH):
        self.path = Path(path)
        self.config = self.load()

    def load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except Exception as e:
                debug_log(f"Failed to load config: {e}")
                return {}
        return {}

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            debug_log(f"Failed to save config: {e}")

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

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, timeout: int = 5) -> Optional[Any]:
        if not self.api_base:
            return None
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        debug_log(f"Request: {method} {url}")
        try:
            if method.upper() == "POST":
                resp = requests.post(url, json=data, timeout=timeout)
            else:
                resp = requests.get(url, params=params, timeout=timeout)
            
            if resp.status_code == 200:
                return resp.json()
            else:
                debug_log(f"Request failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            debug_log(f"Request failed: {e}")
        return None

    def get_health(self) -> bool:
        res = self._request("GET", "health", timeout=2)
        return res is not None and res.get("status") == "OK"

    def get_chat(self, message: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "chat", data={"message": message}, timeout=180)

    def get_providers(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "providers", timeout=5)

    def set_provider_mode(self, mode: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "provider/mode", data={"mode": mode}, timeout=5)

    def get_models(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "models", timeout=5)

    def set_model(self, model: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "model/set", data={"model": model}, timeout=5)

    def set_profile(self, profile: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "model/profile", data={"profile": profile}, timeout=5)

    def run_bench(self, quick: bool = True) -> Optional[Dict[str, Any]]:
        return self._request("POST", "model/bench", data={"quick": quick}, timeout=300)

    def get_recommendation(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "model/recommendation", timeout=300)

    def get_missing_models(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "model/missing", timeout=5)

    def test_model(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "model/test", timeout=100)

    def get_context(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "context", timeout=5)

    def reload_context(self) -> Optional[Dict[str, Any]]:
        return self._request("POST", "context/reload", timeout=5)

    def get_status(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "status", timeout=5)

    def get_projects(self) -> Optional[List[Dict[str, Any]]]:
        return self._request("GET", "projects", timeout=5)

    def save_memory(self, content: str, category: str = "general") -> Optional[Dict[str, Any]]:
        return self._request("POST", "memory/remember", data={"content": content, "category": category}, timeout=5)

    def search_memory(self, query: str) -> Optional[List[Dict[str, Any]]]:
        return self._request("GET", "memory/recall", params={"q": query}, timeout=5)

    def get_whereleftoff(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "whereleftoff", timeout=5)

    def get_handoff(self, target: str, context: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "handoff/agent-prompt", data={"target": target, "context": context}, timeout=5)

    def get_search_status(self) -> Optional[Dict[str, Any]]:
        return self._request("GET", "search/status", timeout=5)

    def run_search_export(self, project: str, repo_path: str) -> Optional[Dict[str, Any]]:
        return self._request("POST", "search/export", data={"project": project, "repo_path": repo_path}, timeout=60)

    def run_search_query(self, query: str, project: Optional[str] = None, limit: int = 5) -> Optional[Dict[str, Any]]:
        return self._request("POST", "search/query", data={"query": query, "project": project, "limit": limit}, timeout=10)

def parse_command(line: str) -> Tuple[Optional[str], List[str]]:
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
    
    aliases = {
        "h": "help",
        "s": "status",
        "p": "projects",
        "lo": "leftoff",
        "r": "recall",
        "m": "model",
        "q": "exit",
        "quit": "exit",
        "prof": "profile",
        "pro": "profile",
        "ctx": "context"
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

    def start_server(self, wait_timeout: int = 15):
        if self.client.get_health():
            debug_log("Server already healthy.")
            return True

        debug_log(f"Starting Marius API on port {DEFAULT_PORT}...")
        print(f"Starting Marius API on port {DEFAULT_PORT}...")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        
        venv_python = self.repo_root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            debug_log("Venv python not found, using system python.")
            venv_python = Path(sys.executable)

        cmd = [
            str(venv_python), "-m", "uvicorn", "src.warden.app:app",
            "--host", "127.0.0.1", "--port", str(DEFAULT_PORT),
            "--log-level", "warning"
        ]
        
        debug_log(f"Executing: {' '.join(cmd)}")
        log_file = open(LOG_PATH, "a")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.repo_root),
                stdout=log_file,
                stderr=log_file,
                preexec_fn=os.setsid,
                env={**os.environ, "PYTHONPATH": f"{self.repo_root}:{self.repo_root}/src"}
            )
            
            with open(PID_PATH, "w") as f:
                f.write(str(proc.pid))
            debug_log(f"Started process with PID {proc.pid}")
        except Exception as e:
            print(f"Failed to launch uvicorn: {e}")
            return False
            
        start_time = time.time()
        while time.time() - start_time < wait_timeout:
            if self.client.get_health():
                print("Marius API is online.")
                return True
            time.sleep(0.5)
            
        print(f"Error: Marius API failed to start within {wait_timeout}s. Check logs at {LOG_PATH}")
        return False

    def stop_server(self):
        if PID_PATH.exists():
            try:
                with open(PID_PATH, "r") as f:
                    pid_str = f.read().strip()
                if not pid_str:
                    PID_PATH.unlink()
                    return
                pid = int(pid_str)
                debug_log(f"Stopping PID {pid}...")
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                print(f"Stopped Marius API (PID {pid})")
                PID_PATH.unlink()
            except ProcessLookupError:
                debug_log("Process not found, removing stale PID file.")
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
                pid = f.read().strip()
                if pid:
                    print(f"PID: {pid}")
        
        if online:
            status = self.client.get_status()
            if status and "model_backend" in status:
                diag = status["model_backend"]
                print(f"Provider: {diag.get('active_provider')}")
                print(f"Model: {diag.get('configured_model')}")

    def doctor(self, show_model: bool = False):
        print("Marius Doctor Diagnostics")
        print("-" * 30)
        print(f"Repo Root: {self.repo_root}")
        
        launcher_path = self.repo_root / "scripts" / "marius"
        print(f"Launcher: {launcher_path} ({'Executable' if os.access(launcher_path, os.X_OK) else 'NOT EXECUTABLE'})")
        
        wrapper_path = Path.home() / ".local" / "bin" / "marius"
        if wrapper_path.exists():
            print(f"Wrapper: {wrapper_path}")
            try:
                with open(wrapper_path, "r") as f:
                    content = f.read()
                if str(self.repo_root) in content:
                    print("  Status: Points to correct repo root.")
                else:
                    print("  Status: STALE or points elsewhere.")
            except Exception:
                print("  Status: Could not read wrapper.")
        else:
            print(f"Wrapper: {wrapper_path} (NOT INSTALLED)")

        venv_python = self.repo_root / ".venv" / "bin" / "python"
        print(f"Venv Python: {'Found' if venv_python.exists() else 'Not Found (using system)'}")
        print(f"Config Path: {CONFIG_PATH} ({'Exists' if CONFIG_PATH.exists() else 'Missing'})")
        print(f"PID File: {PID_PATH} ({'Exists' if PID_PATH.exists() else 'Missing'})")
        print(f"Log Path: {LOG_PATH}")
        
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', DEFAULT_PORT))
        print(f"Port {DEFAULT_PORT}: {'Busy' if result == 0 else 'Free'}")
        sock.close()
        
        print(f"API Base: {self.client.api_base}")
        health = self.client.get_health()
        print(f"Health Check: {'OK' if health else 'FAILED'}")
        
        if not health and self.client.api_base != DEFAULT_API_BASE:
            print(f"  Note: Current API base is {self.client.api_base}, but default is {DEFAULT_API_BASE}.")
            temp_client = ApiClient(DEFAULT_API_BASE)
            if temp_client.get_health():
                print(f"  Suggestion: The server seems to be running on the default port. Run '/api {DEFAULT_API_BASE}' to fix.")

        if health:
            status = self.client.get_status()
            if status and "model_backend" in status:
                diag = status["model_backend"]
                reachable = diag.get('ollama_reachable')
                print(f"Ollama Reachable: {'Yes' if reachable else 'No'}")
                if reachable:
                    model = diag.get('configured_model')
                    available = diag.get('available_models', [])
                    print(f"Configured Model: {model}")
                    print(f"Model Installed: {'Yes' if model in available or f'{model}:latest' in available else 'No'}")
                    if show_model:
                        self.handle_model_test()
        
        print(f"Command Parser: {'Functional' if parse_command('/status')[0] == 'status' else 'BROKEN'}")
        print("-" * 30)

    def tail_logs(self, follow: bool = False):
        if not LOG_PATH.exists():
            print("No log file found.")
            return
        if follow:
            print(f"Tailing logs at {LOG_PATH} (Ctrl+C to stop)...")
            try:
                subprocess.run(["tail", "-n", "50", "-f", str(LOG_PATH)])
            except KeyboardInterrupt:
                print()
        else:
            print(f"Recent logs from {LOG_PATH}:")
            subprocess.run(["tail", "-n", "50", str(LOG_PATH)])

    def handle_chat(self, message: str):
        self.session_stats["messages_sent"] += 1
        result = self.client.get_chat(message)
        if result:
            warning = result.get("warning")
            if warning:
                print(f"\n[WARNING] {warning}")
                
            response = result.get("response", "No response.")
            provider = result.get("provider", "unknown")
            model = result.get("model", "")
            elapsed = result.get("elapsed", "?")
            print(f"\nmarius> {response}")
            footer = f"provider: {provider}"
            if model: footer += f" | model: {model}"
            footer += f" | {elapsed}s"
            print(f"[{footer}]\n")
        else:
            print("\nError: API offline or request timed out.\n")

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
            print("  /search status      - View brain search status")
            print("  /search export <p>  - Export project for brain index")
            print("  /search query <q>   - Query project brain memory")
            print("  /providers          - Show model providers")
            print("  /provider <mode>    - Set mode (local|cloud|auto)")
            print("  /models             - Show current model & profiles")
            print("  /model set <name>   - Set current model (or 'auto')")
            print("  /model recommend    - Get model recommendation")
            print("  /model apply-recommendation - Apply recommendation")
            print("  /profile <name>     - Set profile (fast|balanced|code|deep)")
            print("  /bench [quick|full] - Run local model benchmark")
            print("  /bench recommend    - Run benchmark and show recommendation")
            print("  /context (/ctx)     - Show grounding facts")
            print("  /context reload     - Reload grounding pack")
            print("  /modeltest          - Run a model self-test")
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
        elif cmd == "search": self.handle_search(args[0])
        elif cmd == "providers": self.handle_providers()
        elif cmd == "provider": self.handle_provider(args[0])
        elif cmd == "models": self.handle_models()
        elif cmd == "model": self.handle_model(args[0])
        elif cmd == "profile": self.handle_profile(args[0])
        elif cmd == "bench": self.handle_bench(args[0])
        elif cmd == "context": self.handle_context(args[0])
        elif cmd == "modeltest": self.handle_model_test()
        elif cmd == "test-drive": self.handle_test_drive()
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

    def handle_providers(self):
        result = self.client.get_providers()
        if result:
            print("\n--- Model Providers ---")
            print(f"Current Mode: {result.get('current_mode')}")
            print(f"Allow Cloud: {'Yes' if result.get('allow_cloud') else 'No'}")
            print("\nAdapters:")
            for p in result.get("providers", []):
                cfg = "[Configured]" if p["configured"] else "[Missing Config]"
                loc = "(Local)" if p["local"] else "(Cloud)"
                print(f"  - {p['name']:<12} {loc:<8} {cfg}")
            print()
        else: print("\nError: API offline.\n")

    def handle_provider(self, mode: str = ""):
        if not mode:
            self.handle_providers()
            return
        res = self.client.set_provider_mode(mode)
        if res:
            print(f"Provider mode set to: {res.get('mode')}")
        else:
            print("Error: Could not set provider mode.")

    def handle_models(self, args: str = ""):
        if args == "missing":
            res = self.client.get_missing_models()
            if res:
                print("\n--- Missing Known Models ---")
                for m in res.get("missing", []):
                    print(f"- {m}")
                print()
            else:
                print("Error: API offline.")
            return
        elif args == "pull-suggestions":
            res = self.client.get_missing_models()
            if res:
                print("\nRun these commands to install missing recommended models:")
                for m in res.get("missing", []):
                    print(f"ollama pull {m}")
                print()
            else:
                print("Error: API offline.")
            return
        
        result = self.client.get_models()
        if result:
            print("\n--- Model Status ---")
            print(f"Current Profile: {result.get('current_profile')}")
            print(f"Forced Model: {result.get('forced_model') or 'None (Auto)'}")
            if result.get("available_ollama"):
                print(f"Available Ollama: {', '.join(result.get('available_ollama'))}")
            print()
        else: print("\nModel Status: Unknown (API offline)\n")

    def handle_model(self, args: str = ""):
        if args.startswith("set "):
            new_model = args[4:].strip()
            if not new_model:
                print("Usage: /model set <model_name>")
                return
            res = self.client.set_model(new_model)
            if res:
                print(f"Model set to: {res.get('model')}")
            else:
                print("Error: Could not set model.")
            return
        elif args == "recommend":
            self.handle_bench("recommend")
            return
        elif args == "apply-recommendation":
            res = self.client.get_recommendation()
            if res and res.get("best_terminal_default"):
                model = res["best_terminal_default"]
                print(f"Applying recommended default: {model}")
                self.client.set_model(model)
            else:
                print("Error: No recommendation available. Run /bench recommend first.")
            return
        elif args == "current":
            self.handle_models()
            return
            
        self.handle_models()

    def handle_profile(self, name: str = ""):
        if not name:
            print("Usage: /profile <fast|balanced|code|deep>")
            return
        res = self.client.set_profile(name)
        if res:
            print(f"Profile set to: {res.get('profile')}")
        else:
            print("Error: Could not set profile.")

    def handle_bench(self, args: str = ""):
        quick = "full" not in args
        recommend_only = "recommend" in args
        
        print(f"\nRunning Local Model Benchmark ({'quick' if quick else 'full'})... this will take some time.")
        data = self.client.run_bench(quick=quick)
        if data:
            results = data.get("results", [])
            recs = data.get("recommendations", {})
            
            if not recommend_only:
                print("\n--- Benchmark Results ---")
                print(f"{'Model':<20} {'Time':<8} {'Overall':<8} {'Safety':<8} {'Preview'}")
                print("-" * 70)
                for r in results:
                    print(f"{r['model']:<20} {r['elapsed_seconds']:<8.2f}s {r.get('overall_score', 0):<8.1f} {r.get('safety_score', 0):<8.1f} {r.get('response_preview', '')}")
                print()
                
            print("--- Recommendations ---")
            print(f"Best Terminal Default: {recs.get('best_terminal_default') or 'None'}")
            print(f"Fastest Safe Model:    {recs.get('fastest_safe_terminal_model') or 'None'}")
            print(f"Best Code Model:       {recs.get('best_code_local') or 'None'}")
            
            if recs.get("models_to_avoid_for_default"):
                print(f"Avoid as Default:      {', '.join(recs['models_to_avoid_for_default'])}")
            print()
            
            if recs.get('best_terminal_default'):
                print(f"To apply: /model apply-recommendation")
        else:
            print("Error: Benchmark failed or timed out.")

    def handle_context(self, args: str = ""):
        args = args or ""
        if "reload" in args:
            res = self.client.reload_context()
            if res:
                print(f"Context reload: {res.get('message')}")
            else:
                print("Error: API offline.")
            return

        res = self.client.get_context()
        if res:
            print("\n--- Marius Grounding Facts ---")
            print(res.get("facts", "No facts found."))
            print()
        else:
            print("Error: API offline.")

    def handle_search(self, args: str = ""):
        parts = args.split(maxsplit=1)
        sub = parts[0].lower() if parts else "status"
        val = parts[1] if len(parts) > 1 else ""

        if sub == "status":
            res = self.client.get_search_status()
            if res:
                print(f"\n--- Brain Search Status ---")
                print(f"Requested Provider: {res.get('requested_provider')}")
                print(f"Actual Provider:    {res.get('actual_provider')}")
                if res.get("fallback_reason"):
                    print(f"Fallback Reason:    {res.get('fallback_reason')}")
                
                print(f"Engine ID:          {res.get('engine_id', 'N/A')}")
                print(f"Data Store ID:      {res.get('data_store_id', 'N/A')}")
                if res.get("serving_config_path"):
                    print(f"Serving Config:     {res.get('serving_config_path')}")
                
                if res.get("exports_dir"): print(f"Local Exports:      {res.get('exports_dir')}")
                
                exports = res.get("exports", [])
                if exports:
                    print("\nLocal Indexes:")
                    for e in exports:
                        size_kb = round(e['size_bytes'] / 1024, 1)
                        print(f"  - {e['project']:<15} {size_kb:>6} KB")
                
                print(f"\nReady: {'Yes' if res.get('ready', True) else 'No'}")
                print()
            else: print("Error: API offline.")

        elif sub == "export":
            if not val:
                # Default to current repo if no project name given
                project = "warden"
                repo_path = str(self.repo_root)
            else:
                project = val
                repo_path = str(self.repo_root) # Simplified for now

            print(f"Exporting context for {project}...")
            res = self.client.run_search_export(project, repo_path)
            if res and res.get("ok"):
                size_kb = round(res['size_bytes'] / 1024, 1)
                print(f"Success. Exported {size_kb} KB to brain.")
            else: print("Error: Export failed.")

        elif sub == "query":
            if not val:
                print("Usage: /search query <query> [--project <p>]")
                return
                
            project = None
            query = val
            if "--project" in val:
                q_parts = val.split("--project")
                query = q_parts[0].strip()
                project = q_parts[1].strip()

            res = self.client.run_search_query(query, project=project)
            if res:
                results = res.get("results", [])
                actual_provider = res.get("provider", "unknown")
                print(f"\n--- Brain Search Results ('{query}') ---")
                print(f"Provider: {actual_provider}")
                print("-" * 30)
                
                if not results:
                    print("No relevant memory found.")
                for r in results:
                    p_label = r.get("provider", actual_provider)
                    print(f"[{r['project']}] {r['title']} (Score: {r['score']}) [provider: {p_label}]")
                    print(f"  {r['snippet']}...")
                    print("-" * 20)
                print()
            else: print("Error: API offline.")

    def handle_model_test(self):
        print("\nRunning Model Self-Test...")
        result = self.client.test_model()
        if result:
            ok = result.get("ok", False)
            print(f"Status: {'PASSED' if ok else 'FAILED'}")
            print(f"Provider: {result.get('provider')}")
            print(f"Model: {result.get('model')}")
            print(f"Elapsed: {result.get('elapsed_ms')}ms")
            if not ok:
                print(f"Reason: {result.get('reason')}")
                print(f"Error: {result.get('error')}")
            else:
                print(f"Response: {result.get('response')}")
            print()
        else:
            print("\nError: API offline or test timed out.\n")

    def handle_test_drive(self):
        print("\n=== Marius Experience Lab: Test Drive ===")
        print("This will check your system and find the best model for terminal chat.\n")
        
        self.doctor()
        self.handle_models()
        self.handle_model_test()
        
        print("\nRunning benchmark to find the best model for you...")
        data = self.client.run_bench(quick=True)
        if data:
            recs = data.get("recommendations", {})
            best = recs.get("best_terminal_default")
            fastest = recs.get("fastest_safe_terminal_model")
            
            if best:
                print(f"Your fastest safe terminal model is {fastest}, but {best} scored best overall.")
                print(f"Recommendation: {best} for default chat.")
                print(f"To apply: marius model apply-recommendation")
            else:
                print("No safe models found. Try 'marius models pull-suggestions' to see recommended models.")
        else:
            print("Benchmark failed.")
        
        print("\nTest Drive complete. Enter chat mode with 'marius chat'.\n")

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
    parser.add_argument("command", nargs="?", choices=["start", "stop", "restart", "status", "doctor", "logs", "chat", "model", "modeltest", "providers", "provider", "models", "profile", "bench", "test-drive", "context", "search"], default=None)
    parser.add_argument("subcommand", nargs="?", help="Subcommand (e.g., 'set' for model)")
    parser.add_argument("args", nargs="*", help="Arguments for command")
    parser.add_argument("--once", type=str, help="Run a single chat message and exit")
    parser.add_argument("--api", type=str, help="Marius API base URL")
    parser.add_argument("--follow", action="store_true", help="Follow logs (only for 'logs' command)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--model", action="store_true", help="Include model test (only for 'doctor' command)")
    args, unknown = parser.parse_known_args()
    
    if unknown:
        args.args.extend(unknown)

    if args.debug:
        DEBUG = True

    config = ConfigManager()
    api_base = args.api or os.getenv("MARIUS_API_BASE") or config.get("api_base") or DEFAULT_API_BASE
    
    cli = MariusCLI(api_base)
    
    if args.once:
        if not cli.client.get_health():
            if not cli.start_server():
                sys.exit(1)
        cli.run_command(args.once)
        sys.exit(0)
    
    if args.command == "start":
        cli.start_server()
        sys.exit(0)
    elif args.command == "stop":
        cli.stop_server()
        sys.exit(0)
    elif args.command == "restart":
        cli.stop_server()
        cli.start_server()
        sys.exit(0)
    elif args.command == "status":
        cli.status_server()
        sys.exit(0)
    elif args.command == "doctor":
        cli.doctor(show_model=args.model)
        sys.exit(0)
    elif args.command == "modeltest":
        if not cli.client.get_health():
            if not cli.start_server():
                sys.exit(1)
        cli.handle_model_test()
        sys.exit(0)
    elif args.command == "test-drive":
        if not cli.client.get_health():
            if not cli.start_server():
                sys.exit(1)
        cli.handle_test_drive()
        sys.exit(0)
    elif args.command == "context":
        cli.handle_context(args.subcommand)
        sys.exit(0)
    elif args.command == "search":
        if not cli.client.get_health():
            if not cli.start_server():
                sys.exit(1)
        cli.handle_search(f"{args.subcommand or ''} {' '.join(args.args)}")
        sys.exit(0)
    elif args.command == "model":
        if args.subcommand == "set" and args.args:
            cli.handle_model(f"set {' '.join(args.args)}")
        elif args.subcommand == "recommend":
            cli.handle_model("recommend")
        elif args.subcommand == "apply-recommendation":
            cli.handle_model("apply-recommendation")
        else:
            cli.handle_model()
        sys.exit(0)
    elif args.command == "providers":
        cli.handle_providers()
        sys.exit(0)
    elif args.command == "provider":
        cli.handle_provider(args.subcommand)
        sys.exit(0)
    elif args.command == "models":
        cli.handle_models()
        sys.exit(0)
    elif args.command == "profile":
        cli.handle_profile(args.subcommand)
        sys.exit(0)
    elif args.command == "bench":
        cli.handle_bench()
        sys.exit(0)
    elif args.command == "logs":
        cli.tail_logs(follow=args.follow)
        sys.exit(0)
    elif args.command == "chat":
        cli.repl()
        sys.exit(0)
    
    if args.command is None:
        cli.repl()
        sys.exit(0)
