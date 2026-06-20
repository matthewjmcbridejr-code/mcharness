# Warden (McHarness)

**Warden** is the supervised agent control room from **Marius Systems**. **McHarness** is the local-first engine and API namespace underneath.

## Quick proof

```bash
bash scripts/warden_smoke.sh
```

See [docs/warden_operator_smoke.md](docs/warden_operator_smoke.md) for details.

## UI

```text
http://127.0.0.1:8125/web/warden/index.html
```

## Services

| Port | Mode | Runner | Notes |
|------|------|--------|-------|
| 8124 | Public | Disabled | Read-mostly preview; Codex not runnable |
| 8125 | Private | Enabled | Operator-supervised Codex dispatch |

## Agents (honest status)

- **Codex CLI** — runnable only on private 8125 when the tmux/Codex runner flags are enabled
- **Jules Remote** — connected for planning/status only; not executable yet
- **Captain** — OpenRouter planning on private service; supervised step loop is manual

## Operator workbench highlights

- Mission Control snapshot API (`/api/mcharness/mission-control/snapshot`)
- Mission worklog from real plans, runs, and evidence
- Manual proof gates (approve / block / request more evidence)
- Run review + markdown export
- Agent status refresh without starting tasks

## Safety

- No arbitrary shell execution
- No auto-merge or auto-deploy
- No autonomous multi-step execution
- Public 8124 remains runner-disabled

## Docs

- [docs/warden_operator_smoke.md](docs/warden_operator_smoke.md)
- [docs/warden_mission_control_api.md](docs/warden_mission_control_api.md)
- [docs/warden_repo_layout.md](docs/warden_repo_layout.md)
- [docs/quickstart.md](docs/quickstart.md)
- [SECURITY.md](SECURITY.md)