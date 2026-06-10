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

## Safety

- No env/API keys printed
- No arbitrary shell input
- No auto-merge or auto-deploy
- No public runner exposure
- No service restarts inside the smoke script

## Canonical UI

```text
http://127.0.0.1:8125/web/warden/index.html
```