# McHarness Cockpit API Map

## Goal

Wire a usable local Captain cockpit onto the existing McHarness backend without rebuilding orchestration primitives.

Decision: direct wire the existing Workbench and Captain APIs, with only thin local adapters where the browser needs convenience or persistence help.

## Existing Workbench Routes

Base prefix: `/api/marius/workbench`

### Status and registry

- `GET /status`
  - Returns store status metadata.
- `GET /agents`
- `POST /agents`
- `GET /agents/{agent_id}`
- `GET /skills`
- `POST /skills`
- `GET /skills/{skill_id}`
- `GET /memories`
- `POST /memories`
- `GET /artifacts`
- `POST /artifacts`
- `GET /tools`
- `GET /safety-profiles`

### Threads / sessions

- `GET /threads`
  - Returns thread list as JSON objects.
- `POST /threads`
  - Request: `WorkbenchThreadCreateRequest`
  - Key fields:
    - `thread_id?`
    - `title`
    - `objective?`
    - `goal?`
    - `agent_id?`
    - `status`
    - `next_action`
    - `notes?`
  - Response: thread object with persisted `thread_id`, timestamps, prompt queue, minion tasks, evidence records, hard gates, planned acceptance commands.
- `GET /threads/{thread_id}`
- `GET /threads/{thread_id}/messages`
- `POST /threads/{thread_id}/messages`
  - Request: `WorkbenchMessageCreateRequest`
  - Key fields:
    - `message_id?`
    - `author?`
    - `role?`
    - `kind`
    - `content`
  - Response: `WorkbenchMessage`

### Thread proof gates

- `GET /threads/{thread_id}/proof-gates`
- `POST /threads/{thread_id}/proof-gates`
  - Request: `WorkbenchProofGateCreateRequest`
  - Key fields:
    - `gate_id?`
    - `kind`
    - `reason`
    - `triggered_by`
    - `requires_human`
    - `title?`
- `POST /threads/{thread_id}/proof-gates/{gate_id}/decision`
  - Request: `WorkbenchProofGateDecisionRequest`
  - Key fields:
    - `decision`: `approve | reject | edit_state`
    - `actor`
    - `reviewer_note?`

### Runs

- `POST /threads/{thread_id}/captain-runs`
  - Request: `WorkbenchCaptainRunCreateRequest`
  - Key fields:
    - `objective`
  - Response: Captain state-machine run payload created through Captain Mode.
- `GET /runs`
- `POST /threads/{thread_id}/runs`
  - Request: `WorkbenchRunCreateRequest`
  - Key fields:
    - `run_id?`
    - `title`
    - `current_step`
    - `status`
    - `recovery_hint?`
  - Response: `WorkbenchRun`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `POST /runs/{run_id}/events`
  - Request: `WorkbenchRunEventCreateRequest`
  - Key fields:
    - `event_id?`
    - `event_type`
    - `title`
    - `detail`
    - `severity`
  - Response: updated `WorkbenchRun`
- `GET /runs/{run_id}/evidence`
- `POST /runs/{run_id}/evidence`
  - Request: `WorkbenchEvidenceRecordCreateRequest`
  - Key fields:
    - `evidence_id?`
    - `title`
    - `summary`
    - `source_type`
    - `source_ref?`
    - `verdict`
  - Response: updated `WorkbenchRun`
- `GET /runs/{run_id}/proof-gates`
- `POST /runs/{run_id}/proof-gates`
  - Request: `WorkbenchRunProofGateCreateRequest`
  - Key fields:
    - `gate_id?`
    - `title`
    - `reason`
    - `requires_human`
    - `kind?`
    - `triggered_by?`
  - Response: updated `WorkbenchRun`
- `POST /proof-gates/{gate_id}/decision`
  - Request: `WorkbenchRunProofGateDecisionRequest`
  - Key fields:
    - `decision`: `approved | rejected | edit_requested`
    - `actor`
    - `note?`
  - Response: updated `WorkbenchRun`
- `POST /runs/{run_id}/continue`
  - Response: continuation result from the Workbench run model.

## Existing Captain Routes

Base prefix: `/api/marius/captain`

### Reference and classic run routes

- `GET /runs`
- `GET /templates`
- `GET /templates/{template_id}`
- `POST /runs/from-template`
- `POST /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/evidence`
- `POST /runs/{run_id}/gate`
- `POST /runs/{run_id}/gates/{gate_id}/decision`
- `POST /runs/{run_id}/next`
- `GET /state-machine`

These exist, but the cockpit should prefer the state-machine run flow below.

### Captain state-machine routes used by the cockpit

- `POST /runs/{captain_run_id}/plan`
  - Request: `CaptainPlanRequest`
  - Key fields:
    - `instruction`
  - Response: `CaptainState`
- `POST /runs/{captain_run_id}/queue`
  - Response: `CaptainState`
- `GET /runs/{captain_run_id}/queue`
  - Response: `PromptQueueItem[]`
- `POST /runs/{captain_run_id}/assign-minions`
  - Response: `CaptainState`
- `GET /runs/{captain_run_id}/assignments`
  - Response: `MinionAssignment[]`
- `POST /runs/{captain_run_id}/continue`
  - Response:
    - `status`
    - `reason`
    - `recovery_hint`
    - `state`
- `GET /runs/{captain_run_id}/transitions`
  - Response: `CaptainTransition[]`
- `POST /runs/{captain_run_id}/queue/items`
  - Request: `CaptainQueueItemCreateRequest`
  - Key fields:
    - `title`
    - `prompt`
    - `target_role`
    - `priority`
    - `dependencies[]`
    - `file_scope[]`
    - `forbidden_file_scope[]`
    - `max_attempts`
    - `evidence_required[]`
    - `export_format`
    - `allowed_files[]`
    - `forbidden_actions[]`
    - `acceptance_checks[]`
  - Response: `CaptainState`
- `POST /queue/{queue_item_id}/status`
  - Request: `CaptainQueueItemStatusRequest`
- `POST /queue/{queue_item_id}/export`
  - Response: plain text prompt export
- `POST /runs/{captain_run_id}/assignments/{assignment_id}/evidence`
  - Request: `CaptainAssignmentEvidenceRequest`
  - Key fields:
    - `evidence_summary`
    - `source_ref?`
    - `artifact_refs[]`
    - `verdict`
  - Response: `CaptainState`
- `POST /runs/{captain_run_id}/assignments/{assignment_id}/complete`
  - Request: `CaptainAssignmentCompleteRequest`
  - Key fields:
    - `evidence_summary`
    - `output_summary?`
  - Response: `CaptainState`
- `POST /runs/{captain_run_id}/assignments/{assignment_id}/fail`
  - Request: `CaptainAssignmentFailRequest`
  - Response: `CaptainState`

## UI Actions Mapped To Existing Endpoints

### New Session

1. `POST /api/marius/workbench/threads`
2. `POST /api/marius/workbench/threads/{thread_id}/captain-runs`
3. `POST /api/marius/captain/runs/{captain_run_id}/plan`
4. `POST /api/marius/captain/runs/{captain_run_id}/queue`
5. `POST /api/marius/captain/runs/{captain_run_id}/assign-minions`

### Load Sessions / Select Session / Reload Session

- `GET /api/marius/workbench/threads`
- `GET /api/marius/workbench/threads/{thread_id}`
- `GET /api/marius/workbench/runs`
- `GET /api/marius/captain/runs/{captain_run_id}`
- `GET /api/marius/captain/runs/{captain_run_id}/queue`
- `GET /api/marius/captain/runs/{captain_run_id}/assignments`
- `GET /api/marius/captain/runs/{captain_run_id}/transitions`
- `GET /api/marius/workbench/runs/{run_id}/events`
- `GET /api/marius/workbench/runs/{run_id}/evidence`
- `GET /api/marius/workbench/runs/{run_id}/proof-gates`

### Queue Prompt

- `POST /api/marius/captain/runs/{captain_run_id}/queue/items`

### Preview / Copy / Download Prompt

- `POST /api/marius/captain/queue/{queue_item_id}/export`

Browser handles:
- prompt preview
- clipboard copy
- `.md` download
- local `marked exported` UI state unless persisted as a run event

### Add Evidence

- `POST /api/marius/captain/runs/{captain_run_id}/assignments/{assignment_id}/evidence`
- optional follow-up:
  - `POST /api/marius/captain/runs/{captain_run_id}/assignments/{assignment_id}/complete`

### Gate Decision

- `GET /api/marius/workbench/runs/{run_id}/proof-gates`
- `POST /api/marius/workbench/proof-gates/{gate_id}/decision`

Mapping:
- Approve -> `decision=approved`
- Reject -> `decision=rejected`
- Request more evidence -> `decision=edit_requested`

### Resume

- `POST /api/marius/captain/runs/{captain_run_id}/continue`

### Activity Log

- persisted source:
  - `GET /api/marius/workbench/runs/{run_id}/events`
  - `GET /api/marius/captain/runs/{captain_run_id}/transitions`
- operator actions should also write:
  - `POST /api/marius/workbench/runs/{run_id}/events`

## Missing Endpoints

These are small gaps for a usable cockpit, not new orchestration primitives.

### Needed

- `PATCH /api/marius/workbench/threads/{thread_id}`
  - Needed for pause/stop/session note updates without inventing a new thread.

### Probably not needed if the client derives state cleanly

- `GET /api/marius/workbench/threads/{thread_id}/runs`
  - Optional convenience route if `GET /runs` plus client-side filtering becomes awkward.

### Not needed in this sprint

- SSE / streaming route
- provider config routes
- real worker launch routes
- arbitrary shell execution routes
- auth or billing routes
- memory product expansion routes

## Request / Response Shape Notes

- The Workbench proof-gate decision route and the Captain classic gate-decision route use different enums and field names.
- The Captain state-machine run mirrors into a Workbench run with the same `run_id`, so the cockpit can treat:
  - `captain_run_id` as the state-machine key
  - `run_id` as the linked Workbench run key
- Prompt export is already plain text and should stay that way for the sprint. The browser can download it as `.md`.
- Captain continuation is honest by design:
  - open gate -> blocked
  - rejected / edit-requested gate -> blocked
  - approved gate with plan/queue/assignments present -> `ready_to_continue`
  - no real execution is triggered

## Thin Adapter Decision

Decision: direct wire the existing APIs.

Thin patches allowed:

1. Add `PATCH /threads/{thread_id}` for pause/stop/session metadata updates.
2. Enrich Captain queue export text for `.md` prompt handoff quality.
3. Add a convenience thread-to-runs route only if client filtering proves brittle.

Anything beyond that is out of scope for this sprint.
