# UI Showcase Notes

The cockpit has two modes:

- Live mode fetches the real local backend and shows intentional empty states when data is missing.
- Sample mode is enabled with `?sample=1` or the `Show sample run` button and fills the workspace with demo-only content for screenshots.

Sample UI data is always labeled `Sample UI data — not executed.` and never calls worker launch endpoints or changes backend state.

The browser-served cockpit defaults its API base to the same origin so `http://127.0.0.1:8123/web/mctable-studio/cockpit.html` talks to `http://127.0.0.1:8123/api/...`. The `127.0.0.1:8000` fallback is reserved for file/Tauri mode.
