# Warden (McHarness)

Warden is the supervised agent control room from **Marius Systems**. **McHarness** is the local-first engine underneath.

## UI

```text
http://127.0.0.1:8125/web/warden/index.html
```

## Features

- Mission-first operator shell
- Captain Deck with supervised step loop
- Agent Library (Codex CLI, Jules Remote)
- Run History + Evidence (private 8125)
- Codex Live Monitor

## Safety

- Public 8124: runner-disabled, read-mostly
- Private 8125: Codex dispatch enabled, operator-supervised only
- No arbitrary shell execution

See [docs/warden_repo_layout.md](docs/warden_repo_layout.md), [docs/quickstart.md](docs/quickstart.md), and [SECURITY.md](SECURITY.md).