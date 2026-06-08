# Demo Script

Use this for a live, honest demo of the local cockpit.

## Demo flow

1. Show `Status / Capabilities`.
2. Create a task with `fake-worker-success`.
3. Open the task and inspect `current_step`, `status`, `proof_status`, `worker_run_id`, and `recovery_hint`.
4. Open the worker run and show persisted stdout, stderr, and log text.
5. Approve the task through the decision panel.
6. Create a second task with `fake-worker-fail`.
7. Show the failure path and the `recovery_hint`.
8. Submit a rejection or edit-state decision.
9. Create or attempt an unknown command and show that the API or MCP rejects it.
10. Show that MCP is local-only and that the shell is just a wrapper around the cockpit.
11. Open the Captain Mode templates picker and create a run from one of the built-in JSON templates.
12. Record a manual evidence item, trigger a hard gate, and record the gate decision without unblocking the run.
13. Open the Captain Mode section and show the empty state or the latest run, including sprint goal, prompt queue, minion tasks, evidence records, hard gates, scoped commit plan, and next action.

## What to say out loud

- The system is local-first and supervised.
- The backend owns workflow truth.
- Worker execution is fake-worker-only.
- Real external agents remain disabled.
- Arbitrary command execution remains disabled.
- Captain Mode stores planning state only; it does not execute commands.
- The current release candidate is honest about its limitations.

