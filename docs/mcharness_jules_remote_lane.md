# Jules Remote Lane Design Document

## 1. Product Role
* Jules is a remote async worker lane.
* Codex remains the local/private interactive worker.
* Captain Deck decides whether a plan step should go to Codex or Jules.

## 2. User Flow
* User opens Captain Deck.
* User describes goal.
* Captain creates plan.
* User chooses Codex or Jules for each step, or Captain recommends one.
* Jules receives a bounded remote task.
* Warden tracks session status.
* User reviews/pulls Jules result.
* Codex or user verifies before merge.

## 3. Proposed UI
* Agent Library card: Jules Remote
* Status: connected / not connected
* Start Remote Task
* Recent Jules Sessions
* Pull Result
* View Diff

## 4. Proposed Backend Endpoints

* **GET /api/mcharness/jules/status**
  * Purpose: Check connection and health status of the Jules lane.
  * Request shape: Empty (no body).
  * Response shape: `{ "status": "connected" | "not connected", "last_ping": "timestamp" }`
  * Safety notes: Read-only, no secret exposure.

* **POST /api/mcharness/jules/sessions**
  * Purpose: Start a new remote Jules session for a bounded task.
  * Request shape: `{ "task": "bounded task description" }`
  * Response shape: `{ "session_id": "uuid", "status": "started" }`
  * Safety notes: Task strictly bounded. Cannot execute deploy commands or modify public runtime.

* **GET /api/mcharness/jules/sessions**
  * Purpose: List all active or recent Jules sessions and their states.
  * Request shape: Empty (no body).
  * Response shape: `{ "sessions": [ { "id": "uuid", "task": "...", "status": "running|completed|failed" } ] }`
  * Safety notes: Read-only.

* **POST /api/mcharness/jules/sessions/{id}/pull**
  * Purpose: Pull result patches/diffs from a completed Jules session for review.
  * Request shape: Empty (no body).
  * Response shape: `{ "session_id": "uuid", "diff": "unified diff string", "status": "pulled" }`
  * Safety notes: Does not auto-merge. Must strictly return data for review/evidence.

* **POST /api/mcharness/jules/sessions/{id}/cancel**
  * Purpose: Cancel an ongoing Jules session if supported.
  * Request shape: Empty (no body).
  * Response shape: `{ "session_id": "uuid", "status": "cancelled" }`
  * Safety notes: Fails safe if the agent is already done or cannot be cleanly interrupted.

## 5. Jules Command Model
*(to verify against installed Jules CLI)*
* `jules remote list --repo`
* `jules remote new --repo . --session "<bounded task>"`
* `jules remote list --session`
* `jules remote pull --session <id>`

## 6. Safety Model
* No secrets.
* No public runner enablement.
* No deploy commands.
* No push/merge/rebase/reset.
* Jules tasks must be bounded.
* Jules output must be reviewed before integration.
* Codex/server operator verifies before live deployment.

## 7. Task Selection Rules

### Good for Jules:
* Docs
* Tests
* UI polish
* Isolated code changes
* Research/design docs
* Non-live refactors

### Bad for Jules:
* Tmux runner fixes
* OpenRouter key storage
* Private service deployment
* Nginx/systemd
* Secrets
* Production changes

## 8. First Implementation Milestone
* Status check.
* Start bounded remote session.
* List sessions.
* Pull result.
* Show result as evidence.

## 9. Open Questions
* How Jules auth is handled on server.
* Where session IDs are stored.
* Whether Jules can target branches.
* How to pull patches safely.
* How to handle conflicts with Codex work.
