# McHarness Tauri Shell

This shell is a thin desktop wrapper around the existing local cockpit. It does not implement workflow logic, worker launching, or agent routing.

The shell expects the backend at `http://127.0.0.1:8000` and shows the active backend target in the banner so it is clear that `127.0.0.1` means the machine running the desktop app.

If the backend is offline, the shell shows an offline state instead of fabricating data.

## Run

```bash
cargo run --manifest-path src-tauri/Cargo.toml
```

## Safety model

- Backend URL defaults to `http://127.0.0.1:8000`.
- The shell does not expose arbitrary command entry.
- No real agent launch paths are added.
- The shell only embeds the existing cockpit and reads the existing `/api/marius` backend.

