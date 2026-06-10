#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PYTHON="${WARDEN_SMOKE_PYTHON:-/root/hybrid-agent-os/.venv/bin/python}"
PLAYWRIGHT_SPEC="tests/browser/warden-cockpit.spec.js"

echo "== Warden operator smoke =="
echo "repo: ${ROOT}"
echo "python: ${PYTHON}"

echo
echo "-- compile checks --"
"${PYTHON}" -m py_compile src/warden/api.py src/warden/app.py src/server/api.py
node --check web/warden/app.js
bash -n scripts/warden_smoke.sh
echo "compile: ok"

echo
echo "-- pytest --"
"${PYTHON}" -m pytest -q tests
echo "pytest: ok"

echo
echo "-- playwright --"
npx playwright test "${PLAYWRIGHT_SPEC}" --config=playwright.config.js
echo "playwright: ok"

echo
echo "-- optional live service probes --"
probe_service() {
  local label="$1"
  local url="$2"
  if curl -fsS --max-time 3 "${url}" >/dev/null 2>&1; then
    echo "${label}: ok (${url})"
    return 0
  fi
  echo "${label}: skipped (service not reachable)"
  return 0
}

probe_service "8124 agents" "http://127.0.0.1:8124/api/mcharness/agents" || true
probe_service "8125 agents" "http://127.0.0.1:8125/api/mcharness/agents" || true
probe_service "8125 captain" "http://127.0.0.1:8125/api/mcharness/captain/status" || true
probe_service "8125 warden ui" "http://127.0.0.1:8125/web/warden/index.html" || true

echo
echo "== Warden smoke proof: PASS =="
echo "- compile checks passed"
echo "- pytest passed"
echo "- playwright passed"
echo "- live curls attempted only when services are already running"