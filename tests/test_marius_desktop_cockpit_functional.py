from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from src.marius_desktop.api import ARTIFACT_BODY_ROOT
from src.marius_desktop.captain import CAPTAIN_ROOT
from src.marius_desktop.workbench import WORKBENCH_ROOT
from src.server.api import app


def _reset_runtime_state() -> None:
    for directory in [WORKBENCH_ROOT, CAPTAIN_ROOT, ARTIFACT_BODY_ROOT]:
        if directory.exists():
            shutil.rmtree(directory)


def test_functional_cockpit_page_is_served_with_control_plane_labels():
    client = TestClient(app)
    response = client.get("/web/mctable-studio/cockpit-app.html")
    assert response.status_code == 200
    # Simple Agent Library default (SIMPLE MODE)
    for snippet in [
        "Warden",
        "by Marius Systems",
        "Supervised agent ops",
        "Powered by McHarness",
        "warden-sidebar",
        "nav-tasks",
        "No active task plan yet",
        "settings-captain-status",
        "settings-safety-list",
        "Public runner: Disabled on public service",
        "Private runner: Available only on private service",
        "Arbitrary shell input: Disabled",
        "Agent registration: Private only",
        "Connect local CLI agents and remote workers",
        "Agent Library",
        "Ready to Run",
        "Connected / Setup Complete",
        "Develop Plan",
        "Codex CLI",
        "Use Agent",
        "Add Agent",
        "configuration and connection checks",
        "add-agent-modal",
        "add-agent-step-choose",
        "Test Connection",
        "Captain Deck",
    ]:
        assert snippet in response.text
    for removed_snippet in [
        "SERVER CONTROL PLANE",
        "Advanced / Legacy Cockpit",
    ]:
        assert removed_snippet not in response.text


def test_mcharness_control_plane_loop_persists_after_reload():
    _reset_runtime_state()
    try:
        with TestClient(app) as client:
            repos = client.get("/api/mcharness/repos")
            assert repos.status_code == 200
            assert any(item["path"] == "/root/mcharness-public-export" for item in repos.json()["repos"])

            lanes = client.get("/api/mcharness/agent-lanes")
            assert lanes.status_code == 200
            assert any(item["lane_id"] == "manual_paste" and item["implemented"] for item in lanes.json()["lanes"])

            created = client.post(
                "/api/mcharness/sessions",
                json={
                    "title": "Functional cockpit session",
                    "objective": "Prove the repo/lane/session/manual-result gate loop through the browser-facing cockpit APIs.",
                    "plan_instruction": "Create a bounded queue, collect manual result artifacts, and block continuation until the gate is approved.",
                    "repo_path": "/root/mcharness-public-export",
                    "agent_lane": "manual_paste",
                },
            )
            assert created.status_code == 200, created.text
            created_payload = created.json()
            session_id = created_payload["session_id"]
            run_id = created_payload["run"]["run_id"]
            assert created_payload["thread"]["metadata"]["repo_path"] == "/root/mcharness-public-export"
            assert created_payload["thread"]["metadata"]["agent_lane"] == "manual_paste"

            queued = client.post(
                f"/api/mcharness/sessions/{session_id}/queue",
                json={
                    "title": "Inspect git and tests",
                    "prompt": "Review the current worktree, summarize the diff, and return manual evidence.",
                    "target_role": "reviewer",
                    "file_scope": ["src/marius_desktop/api.py", "web/mctable-studio/cockpit-app.js"],
                    "forbidden_file_scope": ["_mctable/**"],
                    "evidence_required": ["Transcript pasted back.", "Git status captured."],
                    "acceptance_checks": ["Evidence is explicit.", "No arbitrary shell execution."],
                },
            )
            assert queued.status_code == 200, queued.text

            queue = client.get(f"/api/marius/captain/runs/{run_id}/queue")
            assert queue.status_code == 200
            queue_items = queue.json()
            assert queue_items
            queue_item_id = queue_items[0]["queue_item_id"]

            exported = client.post(
                f"/api/mcharness/sessions/{session_id}/prompt-export",
                json={"queue_item_id": queue_item_id, "mark_sent": True},
            )
            assert exported.status_code == 200, exported.text
            prompt_text = exported.json()["prompt_text"]
            for snippet in [
                "# McHarness Bounded Minion Prompt",
                f"- Session id: {session_id}",
                f"- Captain run id: {run_id}",
                f"- Queue item id: {queue_item_id}",
                "## Safety constraints",
                "## Files or areas to inspect",
                "## Acceptance tests",
                "## Required final proof format",
            ]:
                assert snippet in prompt_text

            assignments = client.get(f"/api/marius/captain/runs/{run_id}/assignments")
            assert assignments.status_code == 200
            assignment_rows = assignments.json()
            assert assignment_rows
            assignment_id = assignment_rows[0]["assignment_id"]

            manual_result = client.post(
                f"/api/mcharness/sessions/{session_id}/manual-result",
                json={
                    "assignment_id": assignment_id,
                    "summary": "Manual transcript and repo evidence captured from the selected lane.",
                    "transcript": "Operator pasted the worker transcript here.\nIt includes findings and next steps.",
                    "source_ref": "manual://codex-pasteback",
                    "verdict": "passed",
                    "complete_assignment": True,
                    "git_status": " M src/marius_desktop/api.py",
                    "git_diff_summary": " src/marius_desktop/api.py | 12 ++++++++++--",
                    "test_output": "2 passed in 0.42s",
                },
            )
            assert manual_result.status_code == 200, manual_result.text

            gate_rows = client.get(f"/api/marius/workbench/runs/{run_id}/proof-gates")
            assert gate_rows.status_code == 200
            assert gate_rows.json()

            rejected = client.post(
                f"/api/mcharness/sessions/{session_id}/gate-decision",
                json={"decision": "rejected", "note": "Need a clearer transcript before continuation."},
            )
            assert rejected.status_code == 200, rejected.text

            blocked_continue = client.post(f"/api/marius/captain/runs/{run_id}/continue", json={})
            assert blocked_continue.status_code == 200
            assert blocked_continue.json()["status"] == "blocked"

            approved = client.post(
                f"/api/mcharness/sessions/{session_id}/gate-decision",
                json={"decision": "approved", "note": "Transcript and evidence are sufficient."},
            )
            assert approved.status_code == 200, approved.text

            ready_continue = client.post(f"/api/marius/captain/runs/{run_id}/continue", json={})
            assert ready_continue.status_code == 200
            assert ready_continue.json()["status"] == "ready_to_continue"

            live_git = client.get(f"/api/mcharness/sessions/{session_id}/git-status")
            assert live_git.status_code == 200
            git_payload = live_git.json()
            assert git_payload["repo_path"] == "/root/mcharness-public-export"
            assert "git_status" in git_payload
            assert "git_diff_summary" in git_payload

            artifacts = client.get(f"/api/mcharness/sessions/{session_id}/artifacts")
            assert artifacts.status_code == 200
            artifact_rows = artifacts.json()["artifacts"]
            kinds = {item["kind"] for item in artifact_rows}
            assert "prompt_export" in kinds
            assert "manual_result" in kinds
            assert "git_status" in kinds
            assert "git_diff_summary" in kinds
            assert "test_output" in kinds
            assert "evidence" in kinds
            assert "gate_decision" in kinds
            assert "run_summary" in kinds

            evidence = client.get(f"/api/marius/workbench/runs/{run_id}/evidence")
            assert evidence.status_code == 200
            assert evidence.json()

        with TestClient(app) as reloaded_client:
            thread = reloaded_client.get(f"/api/marius/workbench/threads/{session_id}")
            assert thread.status_code == 200
            assert thread.json()["metadata"]["repo_path"] == "/root/mcharness-public-export"
            assert thread.json()["metadata"]["agent_lane"] == "manual_paste"

            runs = reloaded_client.get(f"/api/marius/workbench/threads/{session_id}/runs")
            assert runs.status_code == 200
            run_rows = runs.json()
            assert run_rows
            assert run_rows[0]["run_id"] == run_id

            artifacts = reloaded_client.get(f"/api/mcharness/sessions/{session_id}/artifacts")
            assert artifacts.status_code == 200
            assert artifacts.json()["artifacts"]

            evidence = reloaded_client.get(f"/api/marius/workbench/runs/{run_id}/evidence")
            assert evidence.status_code == 200
            assert evidence.json()

            gates = reloaded_client.get(f"/api/marius/workbench/runs/{run_id}/proof-gates")
            assert gates.status_code == 200
            assert any(item["status"] == "approved" for item in gates.json())

            events = reloaded_client.get(f"/api/marius/workbench/runs/{run_id}/events")
            assert events.status_code == 200
            titles = {item["title"] for item in events.json()}
            assert "Session created" in titles
            assert "Prompt queued" in titles
            assert "Prompt marked sent" in titles
            assert "Manual result captured" in titles
    finally:
        _reset_runtime_state()
