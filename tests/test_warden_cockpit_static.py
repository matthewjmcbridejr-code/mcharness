from pathlib import Path

from fastapi.testclient import TestClient

from src.server.api import app


ROOT = Path(__file__).resolve().parents[1]
WARDEN_APP = ROOT / "web" / "warden" / "index.html"


def test_warden_app_static_asset_exists():
    assert WARDEN_APP.is_file(), "web/warden/index.html must exist"


def test_warden_app_served_by_api_mount():
    client = TestClient(app)
    warden_response = client.get("/web/warden/index.html")
    assert warden_response.status_code == 200
    assert "Warden" in warden_response.text
    assert "by Marius Systems" in warden_response.text
    assert "Powered by McHarness" in warden_response.text


def test_warden_app_has_control_room_sections():
    content = WARDEN_APP.read_text(encoding="utf-8")
    required_snippets = [
        "Warden",
        "by Marius Systems",
        "Supervise missions, runs, and proof gates.",
        "Control Room",
        "Agent Library",
        "captain-deck-modal",
        "Develop Plan",
        "Deploy Current Step",
        "current-mission-plan",
        "cr-command-center",
        "rail-proof-gates",
        "runner-sessions-table",
        "control-room.js",
        "runs-list",
        "evidence-list",
    ]
    for snippet in required_snippets:
        assert snippet in content, f"Missing Warden UI snippet: {snippet}"

    banned_snippets = [
        "Legacy Cockpit",
        "Marius Desktop",
        "McTable Studio",
        "SERVER CONTROL PLANE",
    ]
    for snippet in banned_snippets:
        assert snippet not in content, f"Legacy product copy found: {snippet}"