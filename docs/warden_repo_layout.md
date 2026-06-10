# Warden repository layout

Warden is the supervised agent control room from Marius Systems. McHarness is the engine and API namespace.

## Runtime layout

```text
src/warden/          # Warden control plane (FastAPI)
src/server/api.py    # Service entrypoint

web/warden/          # Canonical Warden UI
  index.html         # http://127.0.0.1:8125/web/warden/index.html
  app.html
  app.js
  app.css

tests/
  test_warden_*.py
  browser/warden-cockpit.spec.js

docs/
  warden_repo_layout.md
  branding.md
  quickstart.md
```

## Data paths

Runtime state lives under `MCHARNESS_DATA_ROOT` (default `_mctable/`, gitignored):

- `captain/plans.json` — Captain supervised plans
- `mcharness/runners/` — Codex runner session state
- `mcharness/runs/` — Run history
- `mcharness/evidence/` — Evidence records
- `agents/` — Agent registry

## API namespace

Warden UI uses **`/api/mcharness/...`** exclusively.

Legacy `/api/marius` routes are not mounted in the Warden service.