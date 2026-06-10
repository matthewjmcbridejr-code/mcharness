#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PYTHON="${WARDEN_SMOKE_PYTHON:-/root/hybrid-agent-os/.venv/bin/python}"
PLAYWRIGHT_SPEC="tests/browser/warden-cockpit.spec.js"
SERVICE_CHECKS=0
READINESS_TIMEOUT_SEC=10

usage() {
  cat <<'EOF'
Usage: bash scripts/warden_smoke.sh [--service-checks]

  --service-checks   Poll 8124/8125 for up to 10s before live curls.
                     Does not restart services.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service-checks)
      SERVICE_CHECKS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

echo "== Warden operator smoke =="
echo "repo: ${ROOT}"
echo "python: ${PYTHON}"
echo "service_checks: ${SERVICE_CHECKS}"

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

wait_for_service() {
  local label="$1"
  local url="$2"
  local deadline=$((SECONDS + READINESS_TIMEOUT_SEC))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; then
      echo "${label}: ready (${url})"
      return 0
    fi
    sleep 1
  done
  echo "${label}: not reachable after ${READINESS_TIMEOUT_SEC}s (${url})" >&2
  return 1
}

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

if [[ "${SERVICE_CHECKS}" -eq 1 ]]; then
  echo
  echo "-- service readiness checks --"
  wait_for_service "8124 agents" "http://127.0.0.1:8124/api/mcharness/agents"
  wait_for_service "8125 agents" "http://127.0.0.1:8125/api/mcharness/agents"
  wait_for_service "8125 captain" "http://127.0.0.1:8125/api/mcharness/captain/status"
  wait_for_service "8125 warden ui" "http://127.0.0.1:8125/web/warden/index.html"
  echo "service readiness: ok"
else
  echo
  echo "-- optional live service probes --"
  probe_service "8124 agents" "http://127.0.0.1:8124/api/mcharness/agents" || true
  probe_service "8125 agents" "http://127.0.0.1:8125/api/mcharness/agents" || true
  probe_service "8125 captain" "http://127.0.0.1:8125/api/mcharness/captain/status" || true
  probe_service "8125 warden ui" "http://127.0.0.1:8125/web/warden/index.html" || true
fi

echo
echo "== Warden smoke proof: PASS =="
echo "- compile checks passed"
echo "- pytest passed"
echo "- playwright passed"
if [[ "${SERVICE_CHECKS}" -eq 1 ]]; then
  echo "- service readiness checks passed"
else
  echo "- live curls attempted only when services are already running"
fi