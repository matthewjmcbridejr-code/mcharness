# Captain Mode

Captain Mode v0.2 is the supervised local state machine that sits on top of Workbench Core and Run Ledger.

## Flow

`operator instruction -> captain intake -> plan -> prompt queue -> bounded minion assignments -> evidence requirements -> proof gates -> human decision -> blocked or safe continuation`

## Demo

Run the deterministic smoke path:

```bash
PYTHONPATH=. python scripts/demo_captain_mode.py
```

Expected proof output:

- `Captain Mode Demo Smoke`
- a created `captain_run_id`
- prompt queue item counts and statuses
- bounded minion assignment counts and statuses
- exported prompt identifiers and file paths under `/tmp/mcharness-captain-mode-demo/exports/`
- evidence count greater than zero
- `continue results: blocked -> blocked; approved -> ready_to_continue`
- `final Captain state/status: ready_to_continue`

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

- Real external agent launch is disabled.
- Public worker launch is disabled.
- Arbitrary shell execution is disabled.
- `scripts/demo_captain_mode.py` uses local safe functions only and exports text artifacts under `/tmp/mcharness-captain-mode-demo/`.
- Sample UI data stays labeled `Sample UI data — not executed.` in the cockpit.
- Runtime JSON remains ignored under `_mctable/workbench/`.

## Real Vs Demo

- Real: the Captain state machine, plan/queue/assignment persistence, proof gates, and continue transitions are backed by the local API and Workbench store.
- Demo: the smoke script prints a deterministic proof report and writes temporary export text outside the repo.
- Not real: no shell runner, no public worker launch, and no external agent execution.
