# Marius CLI Client

The Marius CLI is a professional terminal-based conversation client for interacting with the Marius resident agent on McServer. It provides a similar experience to `ollama run`, but with integrated access to McServer's memory, project status, and handoff tools.

## Quick Start

Run the client from the project root:

```bash
./scripts/marius
```

Or for a single message:

```bash
./scripts/marius --once "Who are you?"
```

## Features

- **Interactive REPL**: Clean prompt with command history.
- **Resident Context**: Real-time access to server and project status.
- **Memory Management**: Easily save and recall facts.
- **Agent Handoff**: Generate prompts for Codex, Grok, or Antigravity.
- **Safe Tools**: Redacted status and log viewing.

## Commands

| Command | Description |
|---------|-------------|
| `/status` | Show server and project health status |
| `/projects` | List active project cards |
| `/leftoff` | Show the last recorded progress summary |
| `/remember <note>` | Save a durable fact to general memory |
| `/remember <cat>: <note>` | Save a fact under a specific category |
| `/recall <query>` | Search through saved memories |
| `/handoff <target>` | Generate a handoff prompt for a specific agent |
| `/model` | Show current model and provider status |
| `/clear` | Clear the terminal screen |
| `/help` | Show available commands |
| `/exit` | Exit the CLI |

## Configuration

The client defaults to `http://127.0.0.1:8126/api/mcharness/marius`. You can override this using:

- Environment variable: `export MARIUS_API_BASE=http://your-server:port/api/mcharness/marius`
- CLI flag: `./scripts/marius --api http://your-server:port/api/mcharness/marius`

## Requirements

- Python 3.11+
- `requests` library
- `prompt_toolkit` (optional, for enhanced history and editing)
