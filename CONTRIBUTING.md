# Contributing

## Layout

- Product code: `src/warden/`
- Service entry: `src/server/api.py`
- UI: `web/warden/`
- Tests: `tests/test_warden_*.py`, `tests/browser/warden-cockpit.spec.js`

## API

Warden UI uses `/api/mcharness/...` only. Do not reintroduce `/api/marius` route mounts without an explicit migration plan.

## Tests

```bash
pytest -q tests
npx playwright test tests/browser/warden-cockpit.spec.js --config=playwright.config.js
```