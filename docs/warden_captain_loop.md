# Warden’s Captain Loop: Supervised Multi-Step Plan Execution

## 1. Product purpose
The Captain Loop is critical for establishing trust and safety in AI-driven coding. It ensures that the transition towards autonomy is deliberate and supervised.
* The user gives one high-level goal.
* Captain creates a multi-step plan to achieve that goal.
* Agents execute one bounded step at a time, limiting the scope of any potential mistakes.
* Warden watches the agent's output and gathers evidence of success or failure.
* The user acts as the ultimate gatekeeper, approving continue, revise, or stop decisions.
* Full autonomy is intentionally disabled until this supervised loop is proven reliable and safe.

## 2. Current v0 behavior
Currently, Warden operates with limited multi-step coordination:
* Captain generates a multi-step plan based on the user's goal.
* The user can deploy the first prompt of the plan to the Codex runner.
* The Codex Live Monitor opens, allowing the user to watch the agent's output in real-time.
* However, subsequent steps are not automated or formally tracked; the user must manually manage the next steps.

## 3. Proposed v1 Captain Loop
The v1 Captain Loop introduces a structured, supervised workflow for executing multi-step plans. Full auto-continue is not recommended for this version.

**Flow:**
1. **Create Plan**: Captain generates the multi-step plan.
2. **Deploy Step 1**: The user dispatches the first step to the agent.
3. **Monitor output**: The user watches the agent's live execution.
4. **Save Output**: Output is captured and saved as evidence for the step.
5. **Mark Step Done**: The user evaluates the evidence and marks the step as complete.
6. **Deploy Next Step**: The user dispatches the next step in the plan.
7. **Revise Step**: If the output is incorrect, the user can revise the current step.
8. **Stop Plan**: The user can halt the entire plan at any time.

## 4. Step state model
Each step in a plan transitions through various states to clearly indicate its progress:
* **queued**: The step is part of the plan but has not yet been dispatched.
* **dispatched**: The step has been sent to the agent for execution.
* **running**: The agent is currently executing the step.
* **needs_review**: The agent has finished execution, and the output requires user evaluation.
* **passed**: The user has reviewed the output and approved the step as successfully completed.
* **failed**: The step encountered a failure during execution.
* **revised**: The step's prompt or scope was modified after a failure or during review.
* **skipped**: The user chose to bypass this step.
* **stopped**: The plan was halted while this step was active, or before it could begin.

## 5. User controls
The UI will provide explicit, real buttons for managing the execution flow:
* **Deploy Current Step**: Sends the currently active step to the designated agent.
* **Mark Step Done**: Approves the step's completion, allowing progression to the next step.
* **Revise Step**: Opens an interface to edit the current step's prompt or instructions before re-deploying.
* **Deploy Next Step**: Advances the plan to the next queued step and sends it to the agent.
* **Save Output**: Captures the current execution logs/output and attaches it to the step as evidence.
* **Stop Plan**: Immediately halts the execution of the entire plan and stops any running agents.

*(No fake or placeholder buttons should be included in the UI.)*

## 6. Captain decision logic
In future iterations, Captain will assist the user by evaluating the Codex output. For v1, Captain will only *suggest* a decision based on these criteria, leaving the user to click the final gate:
* Did the agent follow the defined scope of the step?
* Did the agent attempt to edit forbidden files?
* Did the agent run the required tests?
* Did the agent produce verifiable proof of success?
* Did the agent ask for permission before taking destructive actions?
* Did the agent encounter a failure or error?

## 7. Backend data model proposal
The following fields are suggested to track plans and steps:

**Plan Record:**
* `plan_id`
* `goal`
* `title`
* `summary`
* `repo_id`
* `created_at`
* `updated_at`
* `current_step_id`
* `steps[]` (Array of Step Records)

**Step Record:**
* `step_id`
* `title`
* `prompt`
* `agent_id`
* `status` (Enum based on State Model)
* `runner_session_id`
* `evidence_ids[]`
* `decision_log[]`

## 8. Backend endpoints proposal

* **`GET /api/mcharness/captain/plans/recent`**
  * **Purpose**: Retrieve a list of recent plans for the dashboard.
  * **Request shape**: Empty (optional pagination parameters).
  * **Response shape**: List of summary Plan Records.
  * **Safety notes**: Read-only, user must be authenticated.

* **`GET /api/mcharness/captain/plans/{plan_id}`**
  * **Purpose**: Fetch the full details and steps of a specific plan.
  * **Request shape**: URL parameter `plan_id`.
  * **Response shape**: Full Plan Record including all Step Records.
  * **Safety notes**: Verify user authorization for the associated repository.

* **`POST /api/mcharness/captain/plans/{plan_id}/steps/{step_id}/dispatch`**
  * **Purpose**: Send a step to the agent for execution.
  * **Request shape**: `{ agent_id: string }`
  * **Response shape**: Updated Step Record with `status: "dispatched"`.
  * **Safety notes**: Must verify the step is in a valid state (`queued` or `revised`) and no other step is currently running.

* **`POST /api/mcharness/captain/plans/{plan_id}/steps/{step_id}/complete`**
  * **Purpose**: Mark a step as successfully passed.
  * **Request shape**: `{ evidence_ids: string[] }`
  * **Response shape**: Updated Step Record with `status: "passed"` and updated Plan Record `current_step_id`.
  * **Safety notes**: Requires explicit user approval; cannot be called automatically.

* **`POST /api/mcharness/captain/plans/{plan_id}/steps/{step_id}/revise`**
  * **Purpose**: Modify a step's prompt or parameters.
  * **Request shape**: `{ new_prompt: string }`
  * **Response shape**: Updated Step Record with `status: "revised"`.
  * **Safety notes**: Cannot revise a step that is `passed` or `running`.

* **`POST /api/mcharness/captain/plans/{plan_id}/stop`**
  * **Purpose**: Halt the entire plan.
  * **Request shape**: `{ reason: string }`
  * **Response shape**: Updated Plan Record with all pending steps marked `stopped`.
  * **Safety notes**: Must forcibly kill any active runner sessions associated with the plan.

## 9. UI proposal
The UI should be simple, functional, and focus on the current active task:
* **Captain Deck** displays the plan's steps in sequential order.
* The **current step** is prominently highlighted.
* Each step clearly displays its current **status** badge (e.g., *Passed*, *Running*, *Queued*).
* The prompt for each step is visible but **collapsible** to save space.
* The active step contains the control buttons: **Deploy**, **Mark Done**, **Revise**, and **Stop**.
* Completed steps display a link to the **evidence** (saved output) that justified their passing.

## 10. Safety rules
To maintain a safe, supervised environment, the following strict rules apply:
* No auto-commit of code changes.
* No auto-merge of branches or pull requests.
* No deployment to external or production environments without explicit user approval.
* No public runner enablement (only safe/private lanes are used).
* No secrets should be exposed, generated, or handled by the agents.
* No arbitrary shell input allowed without user review.
* No automatic progression to the next step if tests fail.
* The user remains the final, absolute gate for all state changes and progressions.

## 11. MVP recommendation
The smallest, most practical first build to deliver value should focus on basic state tracking and manual progression:
* Persist the plan to the database.
* Store and track the `current_step`.
* Implement the "Deploy Next Step" button to manually sequence execution.
* Implement the "Mark Step Done" button to manually progress state.
* Attach saved text output to the completed step as evidence.
* *Omit* the autonomous Captain evaluator logic for this version; rely entirely on the user's manual review.

## 12. Future expansion
Once the MVP is proven, the system can be expanded to include:
* Captain providing automatic review suggestions (acting as a co-pilot for the user).
* Automated proof gates (e.g., verifying a specific file exists).
* Test parsing to automatically flag `failed` or `passed` test runs.
* Jules remote step dispatch for offloading execution.
* Commit approval workflows directly within the step lifecycle.
* Comprehensive run report exports for auditing.
* Evaluation scoring to grade agent performance over time.
