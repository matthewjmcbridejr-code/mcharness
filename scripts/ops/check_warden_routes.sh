#!/bin/bash
# Verify Warden UI and API routes

ROUTES=(
    "http://127.0.0.1:8125/web/warden/index.html"
    "http://127.0.0.1:8125/web/warden/"
    "http://127.0.0.1:8125/api/mcharness/mission-control/snapshot"
)

FAILED=0

for url in "${ROUTES[@]}"; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    if [ "$CODE" == "200" ]; then
        echo "✅ [200] $url"
    else
        echo "❌ [$CODE] $url"
        FAILED=1
    fi
done

# Check public port if listening
if sudo ss -ltnp | grep -q ':8124'; then
    url="http://127.0.0.1:8124/web/warden/"
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    if [ "$CODE" == "200" ]; then
        echo "✅ [200] $url (Public)"
    else
        echo "❌ [$CODE] $url (Public)"
        FAILED=1
    fi
fi

exit $FAILED
