# McHarness Agent Registry

The Agent Registry is the safe foundation for registering CLI and remote coding agents in the McHarness Agent Library. It lets operators name, enable, and track bounded agent profiles without exposing secrets or allowing arbitrary shell execution.

## What it is

- A server-side profile store under `<MCHARNESS_DATA_ROOT>/agents/agents.json`
- A read API for the Agent Library and Captain Deck
- A private-only write API for registering safe, bounded profiles

Agent profiles are metadata only. Secrets such as API keys are never stored in agent profiles.

## CLI vs Remote agents

| Kind | Purpose in this version |
|------|-------------------------|
| `cli` | Local CLI adapters such as Codex CLI |
| `remote` | Remote worker adapters such as Jules Remote |

## Built-in Codex profile

McHarness always returns a built-in Codex profile:

- `id`: `codex_cli`
- `adapter`: `codex_cli`
- `kind`: `cli`
- `status`: `ready` on the private runner service when both `MCHARNESS_TMUX_RUNNER_ENABLED=true` and `MCHARNESS_CODEX_RUNNER_ENABLED=true`
- `status`: `disabled` on the public safe service

Codex remains the only runnable adapter in this version. The existing tmux runner path is unchanged.

## Jules Remote planned profile

Jules Remote can be registered on the private service as a non-runnable profile:

- `adapter`: `jules_remote`
- `status`: `not_configured`
- `runnable`: `false`

This version supports registration and status display only. There is no Jules API key setup, no task start button, and no result pull flow yet.

## Why arbitrary shell commands are not allowed

McHarness is a supervised control room, not a generic remote shell. Allowing arbitrary executable registration would bypass the allowlisted repo and bounded runner model. For that reason:

- `custom_cli` and `custom_remote` are disabled placeholders
- `agy_cli` is planned but not registerable yet
- agent profiles cannot store commands, binaries, or secret credentials

## Private-only registration

Write endpoints are available only when the service is in private runner mode:

- `MCHARNESS_PUBLIC_WRITE_ENABLED=true`
- `MCHARNESS_TMUX_RUNNER_ENABLED=true`
- `MCHARNESS_CODEX_RUNNER_ENABLED=true`

The public safe service on `127.0.0.1:8124` rejects `POST`, `PATCH`, and `DELETE` on `/api/mcharness/agents`.

## Public-safe behavior

On the public service:

- `GET /api/mcharness/agents` still returns the built-in Codex profile
- Codex is reported as disabled / not runnable
- registration attempts are rejected
- no secrets are ever returned in agent responses

## API summary

| Endpoint | Access |
|----------|--------|
| `GET /api/mcharness/agents` | public read |
| `GET /api/mcharness/agents/templates` | public read |
| `GET /api/mcharness/agents/{id}/status` | public read |
| `POST /api/mcharness/agents/{id}/probe` | public read, safe probe only |
| `POST /api/mcharness/agents` | private write only |
| `PATCH /api/mcharness/agents/{id}` | private write only |
| `DELETE /api/mcharness/agents/{id}` | private write only |

## UI behavior

- Agent Library shows the built-in Codex card plus any registered profiles
- **Add Agent** opens a modal with CLI / Remote template choices
- Jules Remote can be saved as a registered profile but is not runnable
- Coming Later templates cannot be saved
- Captain Deck loads its agent dropdown from `/api/mcharness/agents`
- Deploy First Prompt remains enabled only for runnable Codex agents

## Future work

- Jules API key setup and remote execution lane
- AGY CLI adapter once bounded runner support exists
- richer per-agent configure actions where they are real and safe
- probe/status improvements for remote adapters after credential support lands