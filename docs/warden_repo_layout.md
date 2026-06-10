# Warden repository layout

Warden is the supervised agent control room product from Marius Systems. McHarness is the engine and API namespace.

## Runtime layout

```text
src/warden/                 # Primary Python package (control plane)
src/marius_desktop/         # Temporary import shims — migrate callers to src.warden
src/server/api.py           # Service entrypoint (imports src.warden.app)

web/warden/                 # Canonical Warden UI
  index.html                # /web/warden/index.html
  app.html                  # alias
  app.js
  app.css

web/mctable-studio/         # Compatibility URL path (8124/8125 services)
  cockpit-app.html          # /web/mctable-studio/cockpit-app.html
  cockpit-app.js
  cockpit-app.css

docs/archive/legacy/        # Archived Marius Desktop / McTable artifacts
```

## Data paths

Runtime state is stored under `MCHARNESS_DATA_ROOT` (default `_mctable/`):

- `captain/plans.json` — Captain supervised plans
- `mcharness/runners/` — Codex runner session state
- `mcharness/runs/` — Run history
- `mcharness/evidence/` — Evidence records
- `agents/` — Agent registry

These directories are gitignored.

## API namespaces

- `/api/mcharness/...` — McHarness engine (Warden UI primary consumer)
- `/api/marius/...` — Legacy workbench/captain/task graph routes (still mounted for compatibility)

## Compatibility notes

- Keep `/web/mctable-studio/cockpit-app.html` until all systemd/bookmarks migrate.
- `src.marius_desktop` shims re-export `src.warden` modules; remove after import migration.
- Archived public marketing page: `docs/archive/legacy/cockpit-public-demo.html`.
- Archived Tauri shell: `docs/archive/legacy/src-tauri/`.