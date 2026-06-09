# McHarness Captain Deck

Captain Deck is the planning surface in McHarness.

What it does:
- Takes a goal from the operator.
- Calls the server-side OpenRouter API to build a bounded 3-7 step plan.
- Turns each step into a safe Codex dispatch prompt.
- Lets the operator deploy the first prompt into the existing private Codex runner.
- Keeps the rest of the workflow manual for now.

Security:
- The browser never receives the OpenRouter API key.
- Captain is disabled unless `OPENROUTER_API_KEY` is set on the private service.
- Public 8124 remains runner-disabled.
- Private 8125 is the test surface for Matt.

Private service setup:
1. Create an env file on the host:

```bash
sudo mkdir -p /etc/mcharness
sudo nano /etc/mcharness/captain.env
```

2. Add:

```bash
OPENROUTER_API_KEY=...
MCHARNESS_CAPTAIN_MODEL=openrouter/auto
```

3. Restart the private cockpit service:

```bash
sudo systemctl restart mcharness-cockpit-private.service
```

Notes:
- The private service should keep the existing runner flags for Codex.
- Do not paste the API key into the browser.
- Do not commit the key to the repo.
