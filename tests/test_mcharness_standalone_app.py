import json
import struct
from pathlib import Path

from fastapi.testclient import TestClient

from src.marius_desktop.app import app as standalone_app
from src.marius_desktop.branding import PRODUCT_NAME
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

    cockpit_response = client.get("/web/mctable-studio/cockpit.html")
    assert cockpit_response.status_code == 200
    assert "McHarness Cockpit" in cockpit_response.text


def test_branding_and_readme_are_public():
    branding = json.loads((ROOT / "branding.json").read_text(encoding="utf-8"))
    assert branding["product_name"] == "McHarness"
    assert branding["repo_name"] == "mcharness"
    assert PRODUCT_NAME == "McHarness"
    assert "McHarness" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_tauri_icon_is_real_square_placeholder():
    icon_path = ROOT / "src-tauri" / "icons" / "icon.png"
    data = icon_path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert width == height
    assert width >= 512
    assert (width, height) != (1, 1)
