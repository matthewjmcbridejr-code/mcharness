import re
from pathlib import Path

from fastapi.testclient import TestClient

from src.server.api import app


ROOT = Path(__file__).resolve().parents[1]
COCKPIT = ROOT / "web" / "mctable-studio" / "cockpit.html"


def _content() -> str:
    return COCKPIT.read_text(encoding="utf-8")


def test_cockpit_static_asset_exists():
    assert COCKPIT.is_file(), "web/mctable-studio/cockpit.html must exist"


def test_cockpit_served_by_api_mount():
    client = TestClient(app)
    response = client.get("/web/mctable-studio/cockpit.html")
    assert response.status_code == 200
    assert "McHarness" in response.text
    assert "agentic harness" in response.text


def test_cockpit_references_live_marius_endpoints_and_same_origin_base():
    content = _content()
    for endpoint in [
        "/api/marius/status",
        "/api/marius/capabilities",
        "/api/marius/workbench/status",
        "/api/marius/workbench/agents",
        "/api/marius/workbench/threads",
        "/api/marius/workbench/threads/${encodeURIComponent(thread.thread_id)}",
        "/api/marius/workbench/threads/${encodeURIComponent(thread.thread_id)}/messages",
        "/api/marius/workbench/skills",
        "/api/marius/workbench/memories",
        "/api/marius/workbench/artifacts",
        "/api/marius/workbench/tools",
        "/api/marius/workbench/safety-profiles",
        "/api/marius/tasks",
        "/api/marius/captain/runs",
    ]:
        assert endpoint in content, f"Missing endpoint reference: {endpoint}"
    assert "window.location.origin" in content or "location.origin" in content
    assert "http://127.0.0.1:8000" in content
    assert "resolveBackendUrl" in content
    assert "mariusDesktopBackendUrl" in content
    assert "DEFAULT_TAURI_BACKEND" in content


def test_cockpit_command_dropdown_is_fake_worker_only():
    content = _content()
    assert '<select id="command"' in content
    assert 'type="text" id="command"' not in content
    assert 'textarea id="command"' not in content

    select_match = re.search(r'<select id="command"[^>]*>(.*?)</select>', content, re.S)
    assert select_match, "Command dropdown not found"
    option_values = re.findall(r'<option value="([^"]+)"', select_match.group(1))
    assert option_values == [
        "fake-worker-success",
        "fake-worker-fail",
        "fake-worker-sleep",
    ]


def test_cockpit_shows_hermes_workspace_language_and_safety():
    content = _content()
    required_snippets = [
        "McHarness",
        "agentic harness",
        "Workbench Core",
        "workbench-status-note",
        "workbench-agent-list",
        "workbench-thread-list",
        "workbench-message-kind",
        "workbench-tools-list",
        "workbench-safety-profile-list",
        "Captain Mode",
        "bounded minions",
        "proof gates",
        "evidence",
        "human approval",
        "scoped commits",
        "local-first",
        "fake-worker-only",
        "Sample UI data",
        "Show sample run",
        "Tell Captain what to plan next",
        "No arbitrary shell execution",
        "Runs / Agents / Minions",
        "Prompt Queue",
        "Safety Rail",
        "Sample UI data — not executed.",
        "Offline preview mode for screenshots and demos.",
        "grid-template-columns: 280px minmax(0, 1.28fr) 300px",
        "thread-panel",
        "sample-mode-banner",
        ".sample-mode .rail > .panel:nth-child(2)",
        ".composer textarea { min-height: 58px; resize: none; }",
        ".inspector .list-item",
        ".inspector .mini-row",
        "command_request` is blocked",
    ]
    for snippet in required_snippets:
        assert snippet in content
    for blocked_launch_button in [
        "launch-codex",
        "launch-agy",
        "launch-grok",
        "launch-claude",
    ]:
        assert blocked_launch_button not in content.lower()
    assert "shell=True" not in content
    assert "dangerously-skip-permissions" not in content
    assert "--yolo" not in content
    assert "--always-approve" not in content


def test_readme_and_showcase_docs_are_updated():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    screenshots = (ROOT / "docs" / "screenshots" / "README.md").read_text(encoding="utf-8")
    showcase_notes = (ROOT / "docs" / "ui_showcase_notes.md").read_text(encoding="utf-8")

    assert "Showcase cockpit" in readme
    assert "Sample UI data — not executed." in readme
    assert "http://127.0.0.1:8123/web/mctable-studio/cockpit.html?sample=1" in screenshots
    assert "Sample UI data — not executed." in screenshots
    assert "live mode" in showcase_notes.lower()
    assert "sample mode" in showcase_notes.lower()
