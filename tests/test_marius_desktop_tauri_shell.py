import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_DIR = ROOT / "docs" / "archive" / "legacy" / "src-tauri"
ARCHIVED_DOCS = ROOT / "docs" / "archive" / "legacy" / "marius_desktop_tauri.md"


def test_archived_tauri_config_exists_and_uses_local_frontend():
    config = json.loads((TAURI_DIR / "tauri.conf.json").read_text(encoding="utf-8"))

    assert config["productName"] == "McHarness"
    assert config["build"]["frontendDist"] == "frontend"
    assert config["app"]["windows"][0]["url"] == "index.html"
    icon_path = TAURI_DIR / "icons" / "icon.png"
    assert icon_path.exists()
    data = icon_path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert width == height
    assert width >= 512
    assert (width, height) != (1, 1)


def test_archived_tauri_shell_references_legacy_cockpit_path():
    html = (TAURI_DIR / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "http://127.0.0.1:8000" in html
    assert "/web/mctable-studio/cockpit.html" in html
    assert "api/marius/status" in html
    assert "Active backend target" in html
    assert "resolveBackendUrl" in html


def test_archived_tauri_shell_docs_exist():
    docs = ARCHIVED_DOCS.read_text(encoding="utf-8")
    assert "cargo run --manifest-path src-tauri/Cargo.toml" in docs
    assert "http://127.0.0.1:8000" in docs
    assert "offline state" in docs.lower()