# Warden Run History and Evidence

## 1. Product purpose
Run History and Evidence is a critical feature for Warden because it provides transparency and accountability for AI coding agent activities. Users need to know exactly what happened during a run. Prompts, transcripts, diffs, tests, and human decisions must be reviewable. Warden is a supervised control room, not a disposable chat box. This feature ensures that the work produced by agents is verifiable and historically auditable.

## 2. User flow
The typical user flow for interacting with run history and evidence is:
1. The user creates a plan in the Captain Deck.
2. Warden dispatches the prompt to Codex (the live worker lane).
3. Codex executes the task and produces an output.
4. The user reviews and saves the output.
5. Warden records a run summary containing the execution details.
6. The user can reopen the recent run later at any time.
7. The user can review the original prompt, execution transcript, status, test results, files changed, and the collected proof/evidence.

## 3. Proposed UI
The UI should be kept simple and focused on the core functionality:
- **Recent Runs section**: A list showing the most recent runs with their status and basic metadata.
- **Run detail view**: A modal or dedicated view showing the specific details of a single run.
- **Evidence drawer or modal**: A slide-out drawer or modal to view detailed evidence items.
- **Save Output button behavior**: When output is saved, the UI triggers the creation of the run and evidence records.
- **Open Monitor**: A quick action to open the Live Monitor for active, ongoing runs.
- **View Evidence**: An action available on completed runs to inspect the evidence.

## 4. Data model proposal
The backend should support the following fields for a run and its evidence:
- `run_id`: Unique identifier for the run
- `plan_id`: (Optional) Associated Captain Deck plan
- `step_id`: (Optional) Specific step within a plan
- `agent_id`: Identifier of the agent used
- `agent_adapter`: The adapter type (e.g., Codex)
- `repo_id`: The repository being worked on
- `branch`: The branch used for the task
- `title`: A human-readable title for the run
- `prompt`: The actual prompt sent to the agent
- `transcript_path`: Storage path to the full execution transcript
- `transcript_excerpt`: A summarized or shortened version of the transcript for quick viewing
- `status`: Current state (e.g., in-progress, completed, failed)
- `started_at`: Timestamp of when the run started
- `completed_at`: Timestamp of when the run finished
- `files_changed`: List or summary of modified files
- `tests_run`: Information about tests executed and their results
- `proof_summary`: A high-level summary of the evidence
- `evidence_items`: Array of specific evidence details
- `approval_decisions`: Human decisions made regarding the run (e.g., approved, rejected)

## 5. Backend endpoints proposal

**GET /api/mcharness/runs/recent**
- **Purpose**: Fetch a list of recent runs for the UI.
- **Request shape**: `GET` request (optionally with pagination/filtering params like `?limit=10`).
- **Response shape**: Array of run summary objects.
- **Safety notes**: Must respect privacy settings; only return runs the user is authorized to see.

**GET /api/mcharness/runs/{run_id}**
- **Purpose**: Fetch the full details of a specific run.
- **Request shape**: `GET` request with the `run_id` path parameter.
- **Response shape**: A complete run object including the prompt, excerpt, status, etc.
- **Safety notes**: Ensure the requester has access to this specific run.

**POST /api/mcharness/runs/{run_id}/evidence**
- **Purpose**: Add a new piece of evidence to an existing run (e.g., test output, diffs).
- **Request shape**: `POST` request with a JSON body containing the evidence data (type, content, etc.).
- **Response shape**: The created evidence object or a success status.
- **Safety notes**: Only allowed in private mode. Sanitize input to prevent injection.

**GET /api/mcharness/evidence/{evidence_id}**
- **Purpose**: Retrieve a specific piece of evidence by its ID.
- **Request shape**: `GET` request with the `evidence_id` path parameter.
- **Response shape**: The detailed evidence object.
- **Safety notes**: Ensure the requester has access to the run this evidence belongs to.

**POST /api/mcharness/runs/{run_id}/decision**
- **Purpose**: Record a human decision (e.g., approval or rejection) for a run.
- **Request shape**: `POST` request with JSON body `{"decision": "approved" | "rejected", "notes": "..."}`.
- **Response shape**: Success status and updated run object.
- **Safety notes**: Ensure the user has the authority to make decisions. Must not trigger automatic commits or merges.

## 6. Evidence types
The system should support the following types of evidence:
- **prompt**: The original instruction given to the agent.
- **transcript**: The detailed log of the agent's execution.
- **test output**: Results from running the test suite.
- **diff summary**: An overview of the code changes.
- **file list**: A simple list of files touched by the agent.
- **screenshot**: Visual proof, if applicable (e.g., UI changes).
- **PR link**: A link to the generated pull request, if any.
- **human decision**: The record of the user's review and approval/rejection.
- **agent final report**: Any concluding remarks or summary generated by the agent itself.

## 7. Safety and privacy
- **Do not store secrets**: Ensure no API keys, passwords, or sensitive tokens are stored in the run history or evidence.
- **Redact env/API keys**: Automatically redact known sensitive patterns from transcripts and prompts before saving.
- **Public mode read-only**: When operating in public mode, the system must be read-only.
- **Private mode writes evidence**: Evidence generation and writing are restricted to private mode operations.
- **Evidence must not auto-approve commits**: The collection of evidence is for review only and must not automatically approve commits.
- **No auto-merge**: Under no circumstances should the collection of evidence or a successful run trigger an automatic merge of code.

## 8. MVP recommendation
For the initial release, the smallest valuable implementation should include:
- A simple **Recent Runs list**.
- The **Save Output** button that creates a basic evidence record.
- A **Run Detail modal** that displays the prompt, a transcript excerpt, and the run status.
- *Omissions*: No complex evaluations (evals) yet, and no multi-user permission systems.

## 9. Future expansion
Future iterations of the feature could include:
- **Proof gates**: Requiring specific evidence before allowing the next step in a pipeline.
- **Commit approval**: A more formal process for approving changes to be committed.
- **Jules PR evidence**: Integrating evidence directly into Jules-generated Pull Requests.
- **Test result parsing**: Automatically parsing and structuring test outputs for easier reading.
- **Eval scoring**: Assigning automated scores to runs based on predefined criteria.
- **Exportable run report**: The ability to download or share a comprehensive PDF/HTML report of a run.
