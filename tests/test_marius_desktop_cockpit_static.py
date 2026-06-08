import re
from pathlib import Path

from fastapi.testclient import TestClient

from src.server.api import app


COCKPIT = Path("web/mctable-studio/cockpit.html")


def _content() -> str:
    return COCKPIT.read_text(encoding="utf-8")


def test_cockpit_static_asset_exists():
    assert COCKPIT.is_file(), "web/mctable-studio/cockpit.html must exist"


def test_cockpit_served_by_api_mount():
    client = TestClient(app)
    response = client.get("/web/mctable-studio/cockpit.html")
    assert response.status_code == 200
    assert "McHarness Cockpit" in response.text
    assert "/api/marius/status" in response.text


def test_cockpit_references_live_marius_endpoints():
    content = _content()
    for endpoint in [
        "/api/marius/status",
        "/api/marius/capabilities",
        "/api/marius/tasks",
        "/api/marius/captain/templates",
        "/api/marius/captain/runs",
        "/api/marius/captain/runs/from-template",
        "/api/marius/captain/runs/${encodeURIComponent(state.selectedCaptainRunId)}/evidence",
        "/api/marius/captain/runs/${encodeURIComponent(state.selectedCaptainRunId)}/gate",
        "/api/marius/captain/runs/${encodeURIComponent(state.selectedCaptainRunId)}/gates/${encodeURIComponent(state.selectedCaptainGateId)}/decision",
        "/api/marius/tasks/${encodeURIComponent(taskId)}",
        "/api/marius/tasks/${encodeURIComponent(state.selectedTaskId)}/decision",
        "/api/marius/worker-runs/${encodeURIComponent(selectedRunId)}",
        "/api/marius/worker-runs/${encodeURIComponent(selectedRunId)}/logs",
    ]:
        assert endpoint in content, f"Missing endpoint reference: {endpoint}"


def test_cockpit_command_dropdown_is_fake_worker_only():
    content = _content()
    assert '<select id="command"' in content
    assert 'name="command"' in content
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


def test_cockpit_shows_honest_missing_backend_capabilities_and_safety():
    content = _content()
    for snippet in [
        "Backend target",
        "Captain Mode",
        "Captain Mode models supervised work. Real external agent launch is disabled.",
        "No CaptainRun exists yet.",
        "Built-in template",
        "Refresh templates",
        "Create run from template",
        "Captain templates",
        "/api/marius/captain/templates",
        "Manual evidence",
        "Hard gate",
        "Gate decision",
        "Command text only",
        "LangGraph",
        "SQLite checkpointing",
        "No public worker launch",
        "fake-worker-only",
        "No shell=True",
        "MCP local-only",
        "Real agents disabled",
        "planned acceptance commands are stored as text only",
        "This prototype is deliberately thin",
        "status chips and capability cards both mirror the live /api/marius/status and /api/marius/capabilities payloads",
        "resolveBackendUrl",
        "mariusDesktopBackendUrl",
        "localhost",
        "ngrok-free.app",
    ]:
        assert snippet in content
    for blocked_launch_button in [
        "launch-codex",
        "launch-agy",
        "launch-grok",
        "launch-claude",
    ]:
        assert blocked_launch_button not in content.lower()
    assert "execute-command" not in content.lower()
    assert "arbitrary command runner" not in content.lower()
    assert "LangGraph unavailable. SQLite checkpointing unavailable." not in content


def test_cockpit_has_no_captain_command_input():
    content = _content()
    assert 'id="captain-run-select"' in content
    assert 'id="captain-template-select"' in content
    assert 'id="submit-captain-evidence"' in content
    assert 'id="submit-captain-gate"' in content
    assert 'id="submit-captain-gate-decision"' in content
    assert 'id="captain-command"' not in content
    assert 'type="text" id="captain-command"' not in content
    assert "real agent launch button" in content.lower()
