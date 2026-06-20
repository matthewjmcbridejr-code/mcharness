# Warden Control Room Frontend

Warden Control Room v1.5 is the premium operator surface at `/web/warden/index.html`.

## Architecture

- **Shell:** `web/warden/index.html` — sidebar, top bar, center dashboard, right rail
- **Styles:** `web/warden/app.css` — design tokens, layout, screenshot-ready polish
- **Core app:** `web/warden/app.js` — Captain, Codex, agents, runs, evidence, settings flows
- **Control room:** `web/warden/control-room.js` — snapshot polling, hero, tabs, right rail, modals, demo mode

## Data sources

| UI area | API |
|---------|-----|
| Hero / mission progress | `GET /api/mcharness/mission-control/snapshot` |
| Command center tabs | snapshot `timeline`, `plan`, `worklog`, `proof_gates` |
| Right rail agents | snapshot `agents` |
| Right rail safety | snapshot `safety` |
| Runner sessions | `GET /api/mcharness/runner/sessions` |
| Pause mission | `POST /api/mcharness/missions/{id}/pause` (private only) |
| Adjust plan | `POST /api/mcharness/missions/{id}/adjust-plan` (private only) |
| Runner cleanup | `POST /api/mcharness/runner/sessions/cleanup` (private only) |

## Snapshot polling

- Real mode polls every **12 seconds** while Control Room is visible
- Manual **Refresh** in top bar triggers immediate reload
- Polling pauses on non–Control Room sections to avoid hammering the backend

## Real mode vs demo mode

| Mode | Trigger | Data |
|------|---------|------|
| Real (default) | `/web/warden/index.html` | Live API only; honest empty states |
| Demo | `?demo=1` | Local `DEMO_SNAPSHOT` only; banner: “Demo data — simulated for product preview” |

Demo mode never calls cleanup, pause, adjust-plan, or dispatch endpoints.

## Runner session controls

- Inventory from `GET /api/mcharness/runner/sessions`
- **Dry-run cleanup** sends `confirm: false` — shows candidates, kills nothing
- **Confirm cleanup** requires dry-run first + explicit modal; sends `confirm: true`
- Public 8124: cleanup buttons disabled with explanation

## Safety status

Right-rail Safety card renders `snapshot.safety.items[]` — public runner disabled, private runner controlled, Jules planning-only, runner session health, secrets protected.

## Proof gates and evidence

- Proof Gates tab and dedicated view use `snapshot.proof_gates`
- Evidence tab links to Evidence section when empty
- No fake evidence in real mode

## Disabled actions

- Pause / Adjust: disabled without active mission or on public service
- Runner cleanup: private write-enabled only
- Codex dispatch: unchanged existing guards (public runner disabled)
- No auto-dispatch after gate approval

## No-fake-data policy

Real Control Room never injects sample missions, gates, or runner sessions. Demo mode is visibly labeled and opt-in via `?demo=1`.