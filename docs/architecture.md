# Architecture

McHarness is a local-first harness for supervised AI work. The UI is thin; the backend owns workflow truth.

## Layers

```mermaid
flowchart TD
    UI[Browser cockpit / Tauri shell] --> API[FastAPI /api/marius]
    API --> GRAPH[LangGraph workflow truth]
    GRAPH --> DB[SQLite checkpoint store]
    GRAPH --> WORKER[Fake-worker-only runner]
    WORKER --> RUNS[_mctable/worker_runs]
    API --> MCP[Local MCP tools]
```

## Behavior

- The backend owns task state, worker runs, logs, and checkpoint persistence.
- The UI reads real API state instead of inventing fake task data.
- Captain Mode models supervised agentic work with prompt queues, bounded minions, evidence, hard gates, human review, and scoped commits.
- Unsafe legacy launch routes stay disabled.
- Real external agent launch remains disabled.
- Arbitrary command execution remains disabled.
- Unknown commands are rejected through the same allowlist in the API and MCP paths.

