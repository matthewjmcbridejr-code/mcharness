# Warden Proof Gates

## 1. Product purpose
Warden is designed with the core philosophy: **Agent PRs lie. Proof wins.**
Proof gates matter because:
- Agents can claim success falsely.
- Tests may not have been run.
- Files modified may be out of scope.
- Secrets, configurations, and live systems must be protected from unauthorized changes.
- Users need structured, clear evidence before giving approval.

Warden should not trust agent claims unless there is concrete evidence supporting them.

## 2. Gate timing
Proof gates act as checkpoints at critical junctures in a run. They should appear:
- Before dispatching a task to an agent
- After run output is generated
- Before proceeding to the next step
- Before committing code
- Before deploying code
- Before merging or pushing code

## 3. Gate types
The system defines several specialized gate types to handle different categories of verification:
- **Scope gate:** Verifies if changes align with the original prompt.
- **File-change gate:** Checks which files were modified and if they are allowed.
- **Test gate:** Ensures relevant tests have run and passed.
- **Secret/config gate:** Detects unauthorized access or modifications to secrets or configuration.
- **Safety gate:** Prevents dangerous operations or destructive commands.
- **Human approval gate:** Explicit pause requiring a human operator's manual sign-off.
- **Evidence completeness gate:** Verifies that all required evidence types are present before proceeding.

## 4. Evidence inputs
To make decisions, proof gates should evaluate:
- The initial prompt
- Run transcript
- Changed file list
- Diff summary
- Test output
- Exit codes
- Lint output
- Secret scan results
- PR links
- Screenshots
- Agent final report
- Human decision logs

## 5. Gate result model
A proposed data model for a gate result is as follows:
- `gate_id`: Unique identifier
- `run_id`: Associated run
- `plan_id` (optional): Associated plan
- `step_id` (optional): Associated step
- `gate_type`: Type of gate (e.g., test, scope, safety)
- `status`: Current state (`pending`, `passed`, `failed`, `needs_more_evidence`, `blocked`, `overridden`)
- `summary`: Human-readable summary of the gate result
- `evidence_ids`: List of IDs pointing to the evidence gathered
- `created_at`: Timestamp of creation
- `decided_at`: Timestamp of decision
- `decided_by`: Identifier of who/what made the decision
- `decision_reason`: Justification for the decision

## 6. UI proposal
The UI should provide native elements to review and act on gates:
- **Gate Block:** Displayed inside the Mission Worklog.
- **Right Inspector:** Detailed gate summary view.
- **Evidence cards:** Visual representations linked to the specific gate.
- **Action buttons:**
  - Approve next step
  - Block next step
  - Request more evidence
  - Revise prompt
  - Stop run
- **Strictly no hidden auto-approval.** All approvals must be explicit.

## 7. Backend endpoints proposal
The API layer to support proof gates should be minimal and focused:

- `GET /api/mcharness/gates/recent`
  - Purpose: Fetch a list of recent gates for the dashboard.
  - Request shape: `limit` (int), `status` (string filter)
  - Response shape: List of gate objects.
  - Safety notes: Read-only.

- `GET /api/mcharness/runs/{run_id}/gates`
  - Purpose: Get all gates associated with a specific run.
  - Request shape: Path param `run_id`.
  - Response shape: List of gate objects.
  - Safety notes: Read-only.

- `POST /api/mcharness/runs/{run_id}/gates`
  - Purpose: Manually create a new gate for a run.
  - Request shape: `gate_type`, `evidence_ids`, `summary`.
  - Response shape: Created gate object.
  - Safety notes: Requires appropriate roles to create a gate.

- `POST /api/mcharness/gates/{gate_id}/decision`
  - Purpose: Record a decision (pass/fail/block) on a gate.
  - Request shape: `status`, `decision_reason`.
  - Response shape: Updated gate object.
  - Safety notes: Must log the user ID making the decision. Overrides must be explicitly flagged.

- `POST /api/mcharness/gates/{gate_id}/request-evidence`
  - Purpose: Signal that the current evidence is insufficient.
  - Request shape: `requested_evidence_type`, `notes`.
  - Response shape: Updated gate object with new pending status.
  - Safety notes: Automatically halts progression until fulfilled.

## 8. MVP recommendation
The smallest viable build for Proof Gates should include:
- Manual gate creation after a run completes.
- Ability to attach evidence IDs to a gate.
- Basic user decision buttons (Approve, Block).
- A decision log to track who approved/blocked what.
- **Excluded from MVP:** No automatic evaluator, no auto-commit, no auto-merge, no auto-deploy.

## 9. Future evaluator
Later iterations will introduce automated evaluation capabilities:
- Parse test output automatically.
- Detect changed files and compare against allowlists.
- Run inline secret scans.
- Use LLMs to compare the actual scope of work to the original prompt.
- Generate a "Captain recommendation" based on findings.
- **Crucially:** The user remains the final gate; automation only suggests, it does not approve.

## 10. Safety rules
Strict safety protocols govern the Proof Gates system:
- No auto-merge under any circumstances.
- No auto-deploy.
- Zero tolerance for secret exposure (fails secret gate immediately).
- Public mode is read-only or strictly disabled for executions.
- Private mode is the only environment where decision writes are permitted.
- Human final approval is mandatory.
- Any manual override of an automated check failure must be explicitly and permanently logged.
