# Quickstart

## Prerequisites

- Python 3.11+
- Virtualenv with project dependencies (`pip install -e .` or use `/root/hybrid-agent-os/.venv`)

## 1. Start the Warden backend

```bash
cd /root/mcharness-public-export
PYTHONPATH=. uvicorn src.server.api:app --host 127.0.0.1 --port 8125 --reload
```

## 2. Open Warden

```text
http://127.0.0.1:8125/web/warden/index.html
```

Public read-only service (runner disabled) may run on port 8124 via systemd.

## 3. Verify health

```bash
curl -sS http://127.0.0.1:8125/api/mcharness/health
curl -sS http://127.0.0.1:8125/api/mcharness/agents
```

## 4. Run tests

```bash
pytest -q tests
npx playwright test tests/browser/warden-cockpit.spec.js --config=playwright.config.js
```