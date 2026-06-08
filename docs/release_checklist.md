# Release Checklist

## Verified

- [x] Backend routes tested
- [x] LangGraph workflow truth and SQLite checkpointing verified
- [x] Unknown commands rejected through API and MCP
- [x] Fake-worker-only execution verified
- [x] Unsafe launch routes remain disabled
- [x] Local MCP layer verified
- [x] Minimal cockpit exists
- [x] Minimal Tauri shell build verified with `cargo check`
- [x] Bundled Tauri icon is a real square placeholder, not a 1x1 stub

## Before publishing

- [ ] Capture real screenshots only
- [ ] Review README for honest status wording
- [ ] Review SECURITY.md for local-first safety wording
- [ ] Review the X draft for no overclaims
- [ ] Confirm the cockpit and Tauri shell both show the active backend target clearly
- [ ] Confirm no runtime artifacts are staged
- [ ] Confirm no push or deploy step has been performed

