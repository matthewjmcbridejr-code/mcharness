# Warden Operator Smoke

Repeatable local proof for the Warden operator workbench. This script validates compile checks, Python tests, and browser smoke tests. It does **not** restart services, require secrets, or start agent runs.

## Run

From the repo root:

```bash
bash scripts/warden_smoke.sh
```

Optional override for the Python interpreter:

```bash
WARDEN_SMOKE_PYTHON=/path/to/python bash scripts/warden_smoke.sh
```

## What it checks

1. `py_compile` for `src/warden/api.py`, `src/warden/app.py`, `src/server/api.py`
2. `node --check web/warden/app.js`
3. `pytest -q tests`
4. `playwright test tests/browser/warden-cockpit.spec.js`

If services are already running, the script also probes:

- `http://127.0.0.1:8124/api/mcharness/agents` (public, runner-disabled)
- `http://127.0.0.1:8125/api/mcharness/agents` (private, runner-enabled)
- `http://127.0.0.1:8125/api/mcharness/captain/status`
- `http://127.0.0.1:8125/web/warden/index.html`

Skipped curls are normal on a fresh laptop without systemd services.

## Safety

- No env/API keys printed
- No arbitrary shell input
- No auto-merge or auto-deploy
- No public runner exposure

## Canonical UI

```text
http://127.0.0.1:8125/web/warden/index.html
```