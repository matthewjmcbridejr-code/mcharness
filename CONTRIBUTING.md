# Contributing

Keep changes small, local, and reviewable.

- Prefer one measurable target per patch.
- Do not add secrets or deploy config.
- Do not add real agent launch or arbitrary command execution.
- Keep the internal module name `src/marius_desktop` unless the change explicitly requires a migration.
- Run the focused tests for the changed surface before committing.

## Public repo hygiene

- Do not stage runtime artifacts.
- Do not stage `_mctable` checkpoint or worker-run outputs.
- Do not stage `src-tauri/target` or `src-tauri/gen`.

