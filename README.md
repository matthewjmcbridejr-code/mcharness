# McHarness

McHarness is a local-first agentic harness for supervised AI work.

## What it is

McHarness is a local control surface for creating tasks, reviewing worker output, approving or rejecting outcomes, and inspecting persisted logs and checkpoints. The backend truth stays in the FastAPI API, LangGraph workflow, SQLite checkpoint store, fake-worker-only runner, and local MCP layer.

The internal Python module name currently remains `src/marius_desktop` to avoid risky churn during the public export.

## What it is not

- It is not a public SaaS control plane.
- It is not autonomous.
- It does not launch real external agents.
- It does not expose arbitrary shell execution.
- It is not production-readiness proof.

## Current status

- Backend routes are implemented and verified.
- LangGraph workflow truth and SQLite checkpointing are enabled.
- Unknown commands are rejected through both API and MCP.
- Worker execution is fake-worker-only for the current RC.
- Unsafe legacy worker-launch routes remain disabled.
- Captain Mode models supervised agentic work with prompt queues, bounded minions, evidence, hard gates, human review, and scoped commits.
- The minimal web cockpit exists.
- The minimal Tauri shell is verified with `cargo check`.

## Quickstart

Read [docs/quickstart.md](docs/quickstart.md) for the minimal local setup.

## Safety model

Read [SECURITY.md](SECURITY.md) for the local-first safety rules and allowlisted commands.

## Cockpit path

Open the cockpit at:

```text
http://127.0.0.1:8000/web/mctable-studio/cockpit.html
```

## Showcase cockpit

The cockpit is a Hermes-style operator workspace with a toggleable sample run for screenshots and short demos. Sample mode is labeled `Sample UI data — not executed.` and does not trigger worker launches or mutate backend state.

## Tauri shell status

The Tauri shell is a thin local wrapper around the cockpit. It does not add workflow logic or agent launch paths. See [docs/marius_desktop_tauri.md](docs/marius_desktop_tauri.md).

## Known limitations

- No real external agent execution.
- No public worker launch.
- No live trading.
- No fabricated screenshots or adoption claims.
- No public production-readiness claim.
