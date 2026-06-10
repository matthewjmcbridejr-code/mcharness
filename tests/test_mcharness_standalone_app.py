import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.warden.app import app as standalone_app
from src.warden.branding import PRODUCT_NAME
from src.server.api import app


ROOT = Path(__file__).resolve().parents[1]


def test_standalone_app_serves_backend_status_and_web():
    client = TestClient(standalone_app)
    assert app is standalone_app

    status_response = client.get("/api/marius/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["status"] == "online"
    assert status["service"] == "marius-desktop-api"

    warden_response = client.get("/web/warden/index.html")
    assert warden_response.status_code == 200
    assert "Warden" in warden_response.text
    assert "by Marius Systems" in warden_response.text

    compat_response = client.get("/web/mctable-studio/cockpit-app.html")
    assert compat_response.status_code == 200
    assert "Warden" in compat_response.text


def test_branding_and_readme_are_public():
    branding = json.loads((ROOT / "branding.json").read_text(encoding="utf-8"))
    assert branding["product_name"] == "Warden"
    assert branding["repo_name"] == "mcharness"
    assert branding["public_url"] == "https://mctable.team"
    assert PRODUCT_NAME == "Warden"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Warden" in readme
    assert "McHarness" in readme
    assert standalone_app.state.branding["public_url"] == "https://mctable.team"