# McHarness Agent Registry

The Agent Registry is the safe foundation for registering CLI and remote coding agents in the McHarness Agent Library. Add Agent is a configuration wizard: choose an agent, enter required settings, test the configuration, then save only when the profile is useful.

## What it is

- A server-side profile store under `<MCHARNESS_DATA_ROOT>/agents/agents.json`
- A server-side secret store under `<MCHARNESS_DATA_ROOT>/secrets/agent_<agent_id>.json`
- A read API for the Agent Library and Captain Deck
- A private-only write API for configuring safe, bounded profiles

Agent profiles are metadata only. Secrets such as API keys are stored separately and never returned to the browser.

## Add Agent wizard

1. **Choose agent** — Codex CLI (built-in), Jules Remote (configure), or Coming Later placeholders
2. **Configure** — for Jules: display name, API key, optional default repo/branch, require plan approval
3. **Test Connection** — private service only; validates Jules API key against `GET /v1alpha/sources`
4. **Save Agent** — enabled after a successful test, or after explicitly allowing an unverified save when live verification is unavailable

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
- shown as **Installed** in Add Agent
- cannot be registered again
- `status`: `ready` on the private runner service when both `MCHARNESS_TMUX_RUNNER_ENABLED=true` and `MCHARNESS_CODEX_RUNNER_ENABLED=true`
- `status`: `disabled` on the public safe service

Codex remains the only runnable adapter in this version.

## Jules Remote configuration

Jules Remote can be configured on the private service:

- `adapter`: `jules_remote`
- secret stored at `<MCHARNESS_DATA_ROOT>/secrets/agent_<agent_id>.json`
- `connection_status`: `connected`, `unverified`, `invalid_key`, `error`, or `not_configured`
- `runnable`: `false` until Jules execution support lands

Configured Jules agents appear in the Agent Library with **Edit Config** and **Remove**. There is no **Use Agent** button yet.

Captain Deck shows Jules as not runnable with:

> Jules Remote is configured for planning/status only. Execution comes next.

## Why arbitrary shell commands are not allowed

McHarness is a supervised control room, not a generic remote shell. Allowing arbitrary executable registration would bypass the allowlisted repo and bounded runner model. For that reason:

- `custom_cli` and `custom_remote` are disabled placeholders
- `agy_cli` is planned but not registerable yet
- agent profiles and secrets cannot store arbitrary commands

## Private-only registration and configuration

Write endpoints are available only when the service is in private runner mode:

- `MCHARNESS_PUBLIC_WRITE_ENABLED=true`
- `MCHARNESS_TMUX_RUNNER_ENABLED=true`
- `MCHARNESS_CODEX_RUNNER_ENABLED=true`

The public safe service on `127.0.0.1:8124` rejects `POST`, `PATCH`, and `DELETE` on agent registry endpoints.

## Public-safe behavior

On the public service:

- `GET /api/mcharness/agents` still returns the built-in Codex profile
- Codex is reported as disabled / not runnable
- configuration attempts are rejected
- no secrets are ever returned in agent responses

## API summary

| Endpoint | Access |
|----------|--------|
| `GET /api/mcharness/agents` | public read |
| `GET /api/mcharness/agents/templates` | public read |
| `GET /api/mcharness/agents/{id}/status` | public read |
| `POST /api/mcharness/agents/{id}/probe` | public read, safe probe only |
| `POST /api/mcharness/agents/test-config` | private write only; does not persist secrets |
| `POST /api/mcharness/agents` | private write only |
| `PATCH /api/mcharness/agents/{id}` | private write only; safe metadata |
| `PATCH /api/mcharness/agents/{id}/config` | private write only; Jules secret/config |
| `DELETE /api/mcharness/agents/{id}` | private write only |

### Test config response statuses

- `connected` — Jules API accepted the key
- `invalid_key` — Jules API rejected the key
- `not_verified` — structured fallback when live verification is unavailable
- `error` — network or unexpected API failure

## Future work

- Jules session start/list/pull/approve plan
- AGY CLI adapter once bounded runner support exists
- richer per-agent configure actions where they are real and safe