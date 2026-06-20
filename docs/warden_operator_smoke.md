# Warden Operator Smoke

Repeatable local proof for the Warden operator workbench. This script validates compile checks, Python tests, and browser smoke tests. It does **not** restart services, require secrets, or start agent runs.

## Run

From the repo root:

```bash
bash scripts/warden_smoke.sh
```

Optional service readiness checks (poll 8124/8125 for up to 10 seconds before failing):

```bash
bash scripts/warden_smoke.sh --service-checks
```

Use `--service-checks` after manual service restarts or boot so curls wait briefly for readiness instead of failing immediately.

Optional override for the Python interpreter:

```bash
WARDEN_SMOKE_PYTHON=/path/to/python bash scripts/warden_smoke.sh
```

## What it checks

1. `py_compile` for `src/warden/api.py`, `src/warden/app.py`, `src/server/api.py`
2. `node --check web/warden/app.js`
3. `bash -n scripts/warden_smoke.sh`
4. `pytest -q tests`
5. `playwright test tests/browser/warden-cockpit.spec.js`

### Default mode

If services are already running, the script probes (non-fatal):

- `http://127.0.0.1:8124/api/mcharness/agents` (public, runner-disabled)
- `http://127.0.0.1:8125/api/mcharness/agents` (private, runner-enabled)
- `http://127.0.0.1:8125/api/mcharness/captain/status`
- `http://127.0.0.1:8125/web/warden/index.html`

Skipped curls are normal on a fresh laptop without systemd services.

### `--service-checks` mode

Polls each endpoint for up to **10 seconds** before failing. The script never restarts services; restart them separately, then run with `--service-checks`.

When services are reachable, also probes (read-only):

- `http://127.0.0.1:8125/api/mcharness/runner/sessions` — inventory counts only; no cleanup
- `http://127.0.0.1:8125/api/mcharness/safety/status` — includes `runner_sessions` safety item

Runner cleanup is **not** invoked by the smoke script. Use the private cleanup endpoint manually with `confirm=false` (dry-run) before any destructive `confirm=true` cleanup.

## Safety

- No env/API keys printed
- No arbitrary shell input
- No auto-merge or auto-deploy
- No public runner exposure
- No service restarts inside the smoke script
- No runner session cleanup inside the smoke script (inventory read-only)

### Runner session guardrails (operator)

- Managed tmux names: `mch_run_*` only; never `main`, `dev`, `grok`, or numbered shells
- Default max active runner sessions: `4`
- Cleanup: private 8125 only; dry-run by default (`confirm=false`); kills require `confirm=true`
- Dispatch limit error: `Runner session limit reached. Clean stale sessions first.`

## Canonical UI

```text
http://127.0.0.1:8125/web/warden/index.html
```