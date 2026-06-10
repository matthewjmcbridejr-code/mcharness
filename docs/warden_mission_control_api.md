# Warden Mission Control API

Backend aggregation layer for the Warden mission-control mockup. All endpoints live under `/api/mcharness` and use real Captain plans, runs, evidence, proof gates, and agent registry data. No sample or fake records are injected.

## Snapshot

`GET /api/mcharness/mission-control/snapshot`

Returns a single dashboard payload:

- `mission` — title, status, progress %, ETA, current step/agent
- `plan` — Captain plan steps with gate-aware UI status
- `timeline` / `worklog` — recent mission events (redacted)
- `proof_gates` — summary counts + recent gate items
- `agents` — health-oriented agent summary
- `safety` — runner and execution posture
- `next_move` — suggested manual operator action (never auto-executes)

### Mission status rules

| Condition | Status |
|-----------|--------|
| No plan | `idle` |
| Plan exists, no active run | `planned` |
| In-progress step or run | `running` |
| Any blocked gate | `blocked` |
| Any needs-more-evidence gate | `needs_more_evidence` |
| All steps completed | `completed` |
| Plan stopped/paused | `stopped` |

### Public vs private

| Service | Snapshot behavior |
|---------|-------------------|
| 8124 public | Returns honest idle/minimal state; `safety.public_runner_enabled` is `false` |
| 8125 private | Full sanitized snapshot from persisted mission data |

## Agent health

`GET /api/mcharness/agents/health`

Returns `items[]` with:

- Codex CLI — `execution` mode on private when runnable; `disabled` on public
- Jules Remote — `planning_only`, never runnable
- Captain — `orchestrator` when configured
- `active_run_id` / `active_step_id` when an agent is working

## Safety status

`GET /api/mcharness/safety/status`

Returns `secure`, flat safety flags, and human-readable `items[]`:

- Public runner — always disabled
- Private runner — active only on private service with runner flags enabled
- Runner sessions — live `mch_run_*` tmux inventory (`healthy`, `warning`, or `limit_reached`)
- Arbitrary shell input — disabled
- Jules execution — planning only
- Secret exposure — false (responses are redacted)

## Runner session inventory

`GET /api/mcharness/runner/sessions`

Returns sanitized inventory of Warden-managed tmux sessions only:

- Includes sessions matching `mch_run_*` prefix only
- Never includes normal tmux sessions (`main`, `dev`, `grok`, numbered shells, etc.)
- Public 8124 — summary counts and safe fields only (no pane PIDs or command details when runner is disabled)
- Private 8125 — full safe inventory when runner is write-enabled

Response fields:

- `max_active_runner_sessions` — dispatch guard limit (default `4`, override via `MCHARNESS_MAX_ACTIVE_RUNNER_SESSIONS`)
- `total_runner_sessions`, `active_runner_sessions`, `stale_runner_sessions`
- `items[]` — per-session age, stale/active flags, linked run id (no secrets, env vars, or raw tokenized args)

Mission-control snapshot also surfaces `runner_sessions` summary counts under the top-level payload.

## Runner session cleanup

`POST /api/mcharness/runner/sessions/cleanup`

Private/write-enabled only. Public 8124 returns `403`.

Request body:

```json
{
  "confirm": false,
  "stale_after_seconds": 7200
}
```

Behavior:

- Default `confirm=false` — dry-run only; returns `candidates`, `skipped`, `killed` (empty), and `errors` without killing anything
- `confirm=true` — kills only stale, safe-to-manage `mch_run_*` sessions that are not linked to an active run
- Never targets non-`mch_run_*` sessions
- Successful kills append a `runner_sessions_cleaned` worklog/timeline event

## Dispatch guard

Before private Codex dispatch (`POST /api/mcharness/sessions/{id}/runner/start` with `lane_id=codex_cli`), Warden counts live `mch_run_*` sessions. When `active_runner_sessions >= max_active_runner_sessions`, dispatch is rejected with:

`Runner session limit reached. Clean stale sessions first.`

Cleanup dry-run or confirm can reduce the count so dispatch can proceed again. Non-runner flows and `fake_test_lane` are unaffected.

## Mission control actions

Private/write-enabled only. Public 8124 returns `403`.

### Pause mission

`POST /api/mcharness/missions/{mission_id}/pause`

- `mission_id` is the Captain `plan_id`
- Marks the plan stopped and logs `mission_paused` in the worklog
- Does **not** kill tmux/Codex processes automatically

### Adjust plan (stub)

`POST /api/mcharness/missions/{mission_id}/adjust-plan`

- Records `plan_adjustment_requested` in the worklog
- Does **not** rewrite or auto-dispatch plan steps
- Response includes `human_review_required: true`

## Redaction policy

- Transcripts, prompts, gate reasons, and evidence content are redacted via `redact_secrets`
- API keys and secret field names never appear in responses
- Snapshot summaries use excerpts only

## Intentionally not automated

- No auto-dispatch after gate approval
- No autonomous multi-step execution
- No plan rewrite on adjust-plan
- No runner process kill on pause (v1 safe no-op posture)
- No Jules remote execution
- No public runner enablement

## Smoke proof

```bash
bash scripts/warden_smoke.sh
bash scripts/warden_smoke.sh --service-checks   # after service restart
```

Canonical UI: `http://127.0.0.1:8125/web/warden/index.html`