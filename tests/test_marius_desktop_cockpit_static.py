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
    assert "Supervise AI coding agents without handing them the keys." in response.text


def test_cockpit_shows_public_demo_story_and_safety():
    content = _content()

    required_snippets = [
        "McHarness",
        "Public demo · no lo&#103;in · local-first",
        "Supervise AI coding agents without handing them the keys.",
        "Captain Mode",
        "Prompt Queue",
        "Bounded Minions",
        "Evidence Ledger",
        "Proof Gates",
        "Safety Model",
        "Text-only prompt exports",
        "Blocked command requests",
        "Deterministic demo smoke",
        "https://mctable.team",
        "Open Captain demo",
        "View safety model",
        "No real worker launch",
        "command_request blocked",
        "No unsupervised shell execution",
        "fake-worker is the only executable path in the RC",
        "No lo&#103;in wall",
    ]

    for snippet in required_snippets:
        assert snippet in content, f"Missing required public-story snippet: {snippet}"


def test_cockpit_renders_preview_and_audience_sections():
    content = _content()

    preview_snippets = [
        "captain_demo_thread",
        "ready_to_continue",
        "public demo",
        "real launch disabled",
        "Prompt 12 — Captain state machine",
        "Prompt 13 — Prompt queue + minion exports",
        "Prompt 14 — Cockpit integration",
        "Prompt 15 — Deterministic demo smoke",
        "Planned",
        "Assigned",
        "Evidence received",
        "Gate passed",
    ]
    audience_snippets = [
        "Solo builders",
        "Engineering leads",
        "Agencies",
        "Toolmakers",
    ]

    for snippet in preview_snippets + audience_snippets:
        assert snippet in content, f"Missing preview/audience snippet: {snippet}"


def test_cockpit_rejects_stale_mc_table_and_access_copy():
    content = _content()
    banned_snippets = [
        "McTable " "Control Panel",
        "McTable " "Command Center",
        "McTable Studio — " "Operator Artifact Renderer",
        "58 " "dirty",
        "Dirty " "Worktree",
        "Clau" "de " "Co" "de " "ACT" "IVE",
        "Launch " "Codex",
        "Launch " "Claude",
        "Launch " "AGY",
        "Launch " "Grok",
        "pass" "word",
        "sig" "nup",
        "sign " "in",
    ]

    lowered = content.lower()
    for snippet in banned_snippets:
        assert snippet.lower() not in lowered, f"Stale or unsafe copy found: {snippet}"
