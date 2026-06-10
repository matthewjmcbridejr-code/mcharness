from pathlib import Path

from fastapi.testclient import TestClient

from src.server.api import app


ROOT = Path(__file__).resolve().parents[1]
WARDEN_APP = ROOT / "web" / "warden" / "index.html"
COMPAT_APP = ROOT / "web" / "mctable-studio" / "cockpit-app.html"
ARCHIVED_DEMO = ROOT / "docs" / "archive" / "legacy" / "cockpit-public-demo.html"


def test_warden_app_static_asset_exists():
    assert WARDEN_APP.is_file(), "web/warden/index.html must exist"
    assert COMPAT_APP.is_file(), "web/mctable-studio/cockpit-app.html compatibility path must exist"


def test_warden_app_served_by_api_mount():
    client = TestClient(app)
    warden_response = client.get("/web/warden/index.html")
    assert warden_response.status_code == 200
    assert "Warden" in warden_response.text
    assert "by Marius Systems" in warden_response.text
    assert "Powered by McHarness" in warden_response.text

    compat_response = client.get("/web/mctable-studio/cockpit-app.html")
    assert compat_response.status_code == 200
    assert "Warden" in compat_response.text


def test_warden_app_has_control_room_sections():
    content = WARDEN_APP.read_text(encoding="utf-8")
    required_snippets = [
        "Warden",
        "by Marius Systems",
        "Mission Command",
        "Agent Library",
        "Captain Deck",
        "Develop Plan",
        "Deploy Current Step",
        "current-mission-plan",
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


def test_archived_public_demo_preserved_for_reference():
    assert ARCHIVED_DEMO.is_file()
    content = ARCHIVED_DEMO.read_text(encoding="utf-8")
    assert "McHarness" in content
    assert "./cockpit-app.html" in content