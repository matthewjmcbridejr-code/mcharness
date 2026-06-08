# Workbench Core

Run Ledger v0.1 stays local-only under `_mctable/workbench/` and is wired through the public McHarness API.

## Smoke

```bash
curl -s http://127.0.0.1:8123/api/marius/workbench/threads/<thread_id>/runs \
  -H 'Content-Type: application/json' \
  -d '{"title":"Polish cockpit UI","current_step":"plan"}'

curl -s http://127.0.0.1:8123/api/marius/workbench/runs/<run_id>/events \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"plan","title":"Captain plan","detail":"Break the work into bounded checks.","severity":"info"}'

curl -s http://127.0.0.1:8123/api/marius/workbench/runs/<run_id>/evidence \
  -H 'Content-Type: application/json' \
  -d '{"title":"Static tests passed","summary":"Cockpit static tests passed.","source_type":"test","verdict":"passed"}'

curl -s http://127.0.0.1:8123/api/marius/workbench/runs/<run_id>/proof-gates \
  -H 'Content-Type: application/json' \
  -d '{"title":"Human approval before screenshot update","reason":"Screenshot docs should not update until operator approves."}'

curl -s -i http://127.0.0.1:8123/api/marius/workbench/runs/<run_id>/continue
```

## Safety

- `command_request` messages remain blocked.
- Continuation is safe-noop when no blocking proof gate exists.
- Runtime JSON stays ignored under `_mctable/workbench/`.
