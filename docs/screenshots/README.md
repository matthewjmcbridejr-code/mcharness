# Screenshots

Use the McHarness cockpit for README and social screenshots.

## Capture flow

1. Start the local backend.

```bash
PYTHONPATH=. uvicorn src.marius_desktop.app:app --reload --port 8123
```

2. Open the cockpit at `http://127.0.0.1:8123/web/mctable-studio/cockpit.html?sample=1`.
3. Confirm `Show sample run` is visible and the workspace is populated with sample UI data.
4. Capture the page with Playwright.

```bash
npx playwright screenshot http://127.0.0.1:8123/web/mctable-studio/cockpit.html?sample=1 docs/screenshots/cockpit-showcase.png
```

Sample UI data is labeled `Sample UI data — not executed.` and does not mutate backend state.
