# McHarness Release Candidate Report

This public RC keeps the internal module name `src/marius_desktop` for now, while the public identity is McHarness.

## Proven

- Backend routes are live and tested.
- The cockpit is thin and driven by real API data.
- The Tauri shell is local-only.
- Fake-worker-only execution is enforced.
- Unknown commands are blocked.
- Captain Mode models supervised work with prompt queues, bounded minions, evidence, hard gates, human review, and scoped commits.

## Unproven

- Real external agent launch is still disabled.
- Arbitrary command execution is still disabled.
- Public worker launch is still disabled.
- Release packaging and public screenshots remain future work.

