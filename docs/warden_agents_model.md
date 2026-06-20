# Warden Agents Model

Warden organizes agents by **role** and **execution mode**. The Agents page reflects this model so operators know what each agent does and what is safe to run.

## Captain (orchestrator)

**Captain** is Warden's orchestrator agent. Captain plans missions, assigns work to registered agents, tracks proof gates, summarizes evidence, and waits for human approval.

- **Type:** Orchestrator
- **Execution:** None — Captain does not run code or shells
- **Configuration:** OpenRouter model/provider on the private service
- **Instruction profiles:** Markdown-backed profiles (selector + preview on Agents page)

Captain is a first-class card on the **Agents** page. Service-level OpenRouter setup remains in **Settings**, with a link back to Agents → Captain.

## CLI agents

**CLI agents** are local, terminal-backed execution agents supervised by Warden.

Example: **Codex CLI**

- **Type:** CLI Agent
- **Mode:** Private runner only (no public execution)
- **Capabilities:** Code editing, tests, read-only inspection, terminal-monitored work
- **Status:** Ready / Working / Disabled / Error

CLI agents appear under the **CLI Agents** section on the Agents page.

## Remote agents

**Remote agents** are connected hosted agents used for planning, review, or (eventually) remote execution.

Example: **Jules Remote**

- **Type:** Remote Agent
- **Mode:** Planning + status only today
- **Capabilities:** Planning, review, status reports
- **Not executable from Warden yet**

Remote agents appear under the **Remote Agents** section after adapter-based registration and connection checks.

## Markdown instruction profiles

Captain instruction profiles are **fixed, repo-backed markdown files**:

- `docs/warden/agent_profiles/captain-default.md`
- `docs/warden/agent_profiles/captain-code-review.md`
- `docs/warden/agent_profiles/captain-release-manager.md`

The UI loads profiles from the static web bundle (`/web/warden/agent_profiles/…`). Operators can preview, view markdown, copy instructions, and select a profile. Selection is **saved locally** in v1; backend persistence is planned.

**Not allowed in v1:**

- Arbitrary filesystem paths
- Unrestricted file upload
- Reading or displaying secrets

## Why arbitrary agent addition is not implemented

Warden does not expose a generic "add any agent" execution path. Each agent needs an **adapter** with explicit safety boundaries. Ad-hoc fields or shell hooks would bypass proof gates and runner policy.

The **Add Agent** flow is category-based:

1. Add Captain profile (instruction profiles)
2. Add CLI agent — planned
3. Add Remote agent — Jules when registerable
4. Add Read-only research agent — planned

Copy: *"Agent additions are adapter-based. Warden needs a type, capabilities, safety mode, and proof rules before an agent can run."*

## Safety rules for future agent onboarding

Before a new agent can run in Warden:

- No public runner execution unless explicitly designed and gated
- No arbitrary shell input
- No auto-dispatch
- No secrets in UI or logs
- No legacy `/api/marius` or ad-hoc execution bridges

## Future "Add Agent" requirements

A future registry entry must declare:

| Field | Purpose |
|-------|---------|
| Agent type | orchestrator / cli / remote / research |
| Capabilities | What the agent may do (edit, test, plan, review, …) |
| Execution mode | private runner, planning-only, read-only, … |
| Auth requirements | Keys, OAuth, env-only, none |
| Proof gate policy | Which steps require human approval |
| Allowed commands/tools | Bounded tool surface |
| Public/private availability | Which services may register or run the agent |

Until those fields exist in the registry, new agent types remain **planned** or **disabled** in the UI.