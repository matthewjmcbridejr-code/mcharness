import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_DIR = ROOT / "src-tauri"
COCKPIT_PATH = ROOT / "web" / "mctable-studio" / "cockpit.html"


def test_tauri_config_exists_and_uses_local_frontend():
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


def test_tauri_shell_references_cockpit_and_local_backend():
    html = (TAURI_DIR / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "http://127.0.0.1:8000" in html
    assert "/web/mctable-studio/cockpit.html" in html
    assert "api/marius/status" in html
    assert "Active backend target" in html
    assert "`127.0.0.1` means the machine running the desktop app" in html
    assert "resolveBackendUrl" in html
    assert "mariusDesktopBackendUrl" in html
    assert "backend unavailable" in html.lower()


def test_tauri_shell_has_no_arbitrary_command_input_or_agent_launch():
    html = (TAURI_DIR / "frontend" / "index.html").read_text(encoding="utf-8")
    main_rs = (TAURI_DIR / "src" / "main.rs").read_text(encoding="utf-8")

    assert "command" not in html.lower()
    assert "grok-build" not in html.lower()
    assert "codex" not in html.lower()
    assert "agy" not in html.lower()
    assert "shell=True" not in html
    assert "invoke_handler" not in main_rs
    assert "generate_handler" not in main_rs


def test_tauri_shell_docs_exist():
    docs = (ROOT / "docs" / "marius_desktop_tauri.md").read_text(encoding="utf-8")
    assert "cargo run --manifest-path src-tauri/Cargo.toml" in docs
    assert "http://127.0.0.1:8000" in docs
    assert "offline state" in docs.lower()


def test_cockpit_path_still_exists():
    assert COCKPIT_PATH.exists()
