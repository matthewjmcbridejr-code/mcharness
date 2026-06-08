# Security

McHarness is local-first and supervised. The safety model is intentional and narrow:

- Real external agent launch is disabled.
- Arbitrary command execution is disabled.
- Fake-worker-only execution is used for the current RC.
- Unsafe legacy worker-launch routes stay disabled.
- Local MCP tools exist for the local task/worker surface only.
- Captain Mode models supervised agentic work with prompt queues, bounded minions, evidence, hard gates, human review, and scoped commits.

## Secrets and credentials

- Do not add secrets, tokens, API keys, passwords, or credentials to the repo.
- Do not commit `.env` files or production deploy config.

## Reporting

If you find a safety issue, file it privately and describe the exact endpoint, file, or command path involved.

