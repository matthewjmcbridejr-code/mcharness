# Captain Mode

Captain Mode v0.2 is the supervised local state machine that sits on top of Workbench Core and Run Ledger.

## Flow

`operator instruction -> captain intake -> plan -> prompt queue -> bounded minion assignments -> evidence requirements -> proof gates -> human decision -> blocked or safe continuation`

## Smoke

```bash
curl -s http://127.0.0.1:8123/api/marius/captain/state-machine

curl -s http://127.0.0.1:8123/api/marius/workbench/threads/<thread_id>/captain-runs \
  -H 'Content-Type: application/json' \
  -d '{"objective":"Polish cockpit UI for public demo"}'

curl -s http://127.0.0.1:8123/api/marius/captain/runs/<captain_run_id>/plan \
  -H 'Content-Type: application/json' \
  -d '{"instruction":"Create a bounded plan with tests and proof gates."}'

curl -s http://127.0.0.1:8123/api/marius/captain/runs/<captain_run_id>/queue

curl -s http://127.0.0.1:8123/api/marius/captain/runs/<captain_run_id>/assign-minions

curl -s http://127.0.0.1:8123/api/marius/captain/runs/<captain_run_id>/continue
```

## Safety

- No real external agent launch is wired here.
- No public worker launch is wired here.
- No arbitrary shell execution is wired here.
- Sample UI data stays labeled `Sample UI data — not executed.` in the cockpit.
- Runtime JSON remains ignored under `_mctable/workbench/`.
