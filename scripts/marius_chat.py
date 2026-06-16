#!/usr/bin/env python3
import os
import sys
import requests
import argparse
import re
from typing import Optional, Dict, Any, Tuple, List

# Try to import prompt_toolkit for better REPL experience
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

DEFAULT_API_BASE = os.getenv("MARIUS_API_BASE", "http://127.0.0.1:8126/api/mcharness/marius")

class ApiClient:
    def __init__(self, api_base: str):
        self.api_base = api_base.rstrip("/")

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        try:
            if method.upper() == "POST":
                resp = requests.post(url, json=data, timeout=10)
            else:
                resp = requests.get(url, params=params, timeout=10)
            
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to Marius API at {self.api_base}.")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"API Error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

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
    if not line.startswith("/"):
        return None, [line]
    
    parts = line.split(maxsplit=1)
    cmd = parts[0][1:].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if cmd == "remember":
        # Check for category: content
        match = re.match(r"^([^:]+):\s*(.*)$", args)
        if match:
            return cmd, [match.group(1).strip(), match.group(2).strip()]
        return cmd, ["general", args.strip()]
    
    if cmd == "handoff":
        h_parts = args.split(maxsplit=1)
        if len(h_parts) == 2:
            return cmd, [h_parts[0], h_parts[1]]
        return cmd, [args, ""]
        
    return cmd, [args.strip()]

class MariusCLI:
    def __init__(self, api_base: str):
        self.client = ApiClient(api_base)

    def handle_chat(self, message: str):
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

    def handle_projects(self):
        result = self.client.get_projects()
        if result:
            print("\n--- Project Cards ---")
            for p in result:
                print(f"- {p['name']}: {p['description']}")
            print()

    def handle_remember(self, category: str, content: str):
        if not content:
            print("Usage: /remember [category:] <note>")
            return
        result = self.client.save_memory(content, category)
        if result:
            print(f"Memory saved under '{category}'.\n")

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

    def handle_leftoff(self):
        result = self.client.get_whereleftoff()
        if result:
            print("\n--- Where You Left Off ---")
            print(result.get("summary", "No recent progress recorded."))
            print("\nRecent Notes:")
            for note in result.get("recent_notes", []):
                print(f"- {note['date']}: {note['content'].strip()}")
            print()

    def handle_handoff(self, target: str, context: str):
        if not target:
            print("Usage: /handoff <target> [context]")
            return
        result = self.client.get_handoff(target, context)
        if result:
            print(f"\n{result.get('prompt', 'No prompt generated.')}\n")

    def handle_model(self):
        result = self.client.get_status()
        if result:
            # This is a bit of a placeholder as the status doesn't currently return the exact model info 
            # for the chat provider in a direct way, but we can infer or wait for chat.
            print("\nModel Status:")
            print("Provider: Ollama (default)")
            print("Status: Active if Ollama is reachable.\n")
        else:
            print("\nModel Status: Unknown (API offline)\n")

    def run_command(self, line: str) -> bool:
        cmd, args = parse_command(line)
        if cmd is None:
            self.handle_chat(args[0])
            return True
            
        if cmd == "exit":
            return False
        elif cmd == "help":
            print("\nMarius Commands:")
            print("  /status             - Server & Project health")
            print("  /projects           - List active project cards")
            print("  /leftoff           - Get last recorded progress")
            print("  /remember <note>    - Save a durable fact")
            print("  /remember cat: note - Save under specific category")
            print("  /recall <query>     - Search memory")
            print("  /handoff <target>   - Generate handoff prompt")
            print("  /model              - Show current model info")
            print("  /clear              - Clear terminal")
            print("  /help               - Show this help")
            print("  /exit               - Quit\n")
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
        elif cmd == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
        else:
            print(f"Unknown command: /{cmd}. Type /help for available commands.")
        return True

    def repl(self):
        print("Marius Resident Agent")
        print(f"McServer: {self.client.api_base}")
        print("Type /help for commands. Ctrl+C or /exit to quit.\n")
        
        session = None
        if HAS_PROMPT_TOOLKIT:
            history_file = os.path.expanduser("~/.marius_history")
            session = PromptSession(history=FileHistory(history_file))

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
    parser.add_argument("--api", type=str, default=DEFAULT_API_BASE, help="Marius API base URL")
    args = parser.parse_args()

    cli = MariusCLI(args.api)
    if args.once:
        cli.run_command(args.once)
    else:
        cli.repl()
