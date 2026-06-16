#!/usr/bin/env python3
import os
import sys
import requests
import json
import argparse
from typing import Optional, Dict, Any

DEFAULT_API_BASE = os.getenv("MARIUS_API_BASE", "http://127.0.0.1:8126/api/mcharness/marius")

class MariusCLI:
    def __init__(self, api_base: str):
        self.api_base = api_base.rstrip("/")

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None):
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        try:
            if method.upper() == "POST":
                resp = requests.post(url, json=data, timeout=10)
            else:
                resp = requests.get(url, params=params, timeout=10)
            
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to Marius API at {self.api_base}. Is the server running?")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"API Error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

    def chat(self, message: str):
        result = self._request("POST", "chat", data={"message": message})
        if result:
            response = result.get("response", "No response.")
            provider = result.get("provider", "unknown")
            print(f"\n{response}")
            print(f"--- [Provider: {provider}] ---")

    def status(self):
        result = self._request("GET", "status")
        if result:
            print("\n--- System Status ---")
            print(f"Git: {result.get('git', 'N/A')}")
            print(f"Load: {result.get('load', 'N/A')}")
            print("Services:")
            for svc in result.get("services", []):
                print(f"  - {svc['service']}: {svc['status']}")

    def projects(self):
        result = self._request("GET", "projects")
        if result:
            print("\n--- Project Cards ---")
            for p in result:
                print(f"- {p['name']}: {p['description']}")

    def remember(self, category: str, content: str):
        result = self._request("POST", "memory/remember", data={"content": content, "category": category})
        if result:
            print(f"Memory saved under '{category}'.")

    def recall(self, query: str):
        result = self._request("GET", "memory/recall", params={"q": query})
        if result:
            print(f"\n--- Recall Results for '{query}' ---")
            for r in result:
                print(f"- [{r['category']}] {r['content']} ({r['created_at']})")
            if not result:
                print("No matches found.")

    def leftoff(self):
        result = self._request("GET", "whereleftoff")
        if result:
            print("\n--- Where You Left Off ---")
            print(result.get("summary", "No recent progress recorded."))
            print("\nRecent Notes:")
            for note in result.get("recent_notes", []):
                print(f"- {note['date']}: {note['content'].strip()}")

    def repl(self):
        print(f"Marius CLI Connected to {self.api_base}")
        print("Type /help for commands, /exit to quit.\n")
        
        while True:
            try:
                line = input("Marius> ").strip()
                if not line:
                    continue
                
                if line == "/exit":
                    break
                elif line == "/help":
                    print("Commands: /status, /projects, /remember <cat> <content>, /recall <query>, /leftoff, /exit")
                elif line == "/status":
                    self.status()
                elif line == "/projects":
                    self.projects()
                elif line.startswith("/remember"):
                    parts = line.split(maxsplit=2)
                    if len(parts) < 3:
                        print("Usage: /remember <category> <content>")
                    else:
                        self.remember(parts[1], parts[2])
                elif line.startswith("/recall"):
                    parts = line.split(maxsplit=1)
                    if len(parts) < 2:
                        print("Usage: /recall <query>")
                    else:
                        self.recall(parts[1])
                elif line == "/leftoff":
                    self.leftoff()
                elif line.startswith("/"):
                    print("Unknown command. Type /help for available commands.")
                else:
                    self.chat(line)
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
        cli.chat(args.once)
    else:
        cli.repl()
