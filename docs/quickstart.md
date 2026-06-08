# Quickstart

## Prerequisites

- Python environment for the backend and tests
- Rust toolchain for the Tauri shell

## 1. Run the backend verification first

```bash
PYTHONPATH=. python scripts/verify_marius_desktop_backend.py
```

## 2. Start the backend

```bash
PYTHONPATH=. uvicorn src.marius_desktop.app:app --reload
```

## 3. Open the cockpit

```text
http://127.0.0.1:8000/web/mctable-studio/cockpit.html
```

The cockpit shows the active backend target. The default is local, and documented local tunnel URLs are allowed only for manual override.

## 4. Run the Tauri shell

```bash
cargo run --manifest-path src-tauri/Cargo.toml
```

## 5. Use only allowlisted commands

- `fake-worker-success`
- `fake-worker-fail`
- `fake-worker-sleep`

Anything else must be rejected.

