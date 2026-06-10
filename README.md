# Warden (McHarness)

Warden is the supervised agent control room from **Marius Systems**. **McHarness** is the local-first engine underneath — tasks, runs, evidence, Captain plans, and the private Codex runner.

Public demo: [https://mctable.team](https://mctable.team) (read-only / runner-disabled view).

## What it is

- Mission-first operator shell for bounded agent work
- Captain Deck (OpenRouter planning) with supervised step loop
- Agent Library (Codex CLI, Jules Remote configuration)
- Run History + Evidence on the private service (8125)
- Codex Live Monitor for controlled prompt dispatch

## What it is not

- Not a public SaaS control plane with open runner access
- Not autonomous — operators approve each step
- Not arbitrary shell execution
- Not production-readiness proof by itself

## Quickstart

See [docs/quickstart.md](docs/quickstart.md) and [docs/warden_repo_layout.md](docs/warden_repo_layout.md).

## Warden UI paths

Canonical:

```text
http://127.0.0.1:8125/web/warden/index.html
```

Compatibility (services/bookmarks may still use this):

```text
http://127.0.0.1:8125/web/mctable-studio/cockpit-app.html
```

## Safety

See [SECURITY.md](SECURITY.md). Public 8124 remains runner-disabled; private 8125 enables Codex dispatch only.

## Legacy

`src/marius_desktop/` contains temporary import shims. Archived Marius Desktop / McTable artifacts live under `docs/archive/legacy/`.