from pathlib import Path
import shutil

import pytest

from scripts import demo_captain_mode
from src.marius_desktop.captain import CAPTAIN_ROOT
from src.marius_desktop.workbench import WORKBENCH_ROOT


SCRIPT = Path("scripts/demo_captain_mode.py")


@pytest.fixture(autouse=True)
def clean_demo_state():
    for directory in [WORKBENCH_ROOT, CAPTAIN_ROOT, demo_captain_mode.EXPORT_ROOT.parent]:
        if directory.exists():
            shutil.rmtree(directory)
    yield
    for directory in [WORKBENCH_ROOT, CAPTAIN_ROOT, demo_captain_mode.EXPORT_ROOT.parent]:
        if directory.exists():
            shutil.rmtree(directory)


def test_demo_captain_script_imports():
    assert hasattr(demo_captain_mode, "main")


def test_demo_captain_script_has_no_shell_true_or_real_launches():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in content
    for blocked in [
        "launch-codex",
        "launch-agy",
        "launch-grok",
        "launch-claude",
        "grok-build-stub",
        "codex-stub",
        "agy-stub",
        "Claude",
        "AGY",
    ]:
        assert blocked not in content


def test_demo_captain_script_references_safe_captain_endpoints():
    content = SCRIPT.read_text(encoding="utf-8")
    for symbol in [
        "get_status",
        "create_thread",
        "create_captain_state_machine_run",
        "plan_captain_run",
        "queue_captain_run",
        "add_captain_queue_item",
        "assign_captain_minions",
        "export_captain_queue_item",
        "record_captain_assignment_evidence",
        "complete_captain_assignment",
        "decide_run_proof_gate",
        "continue_captain_run",
        "get_captain_run",
        "get_captain_transitions",
    ]:
        assert symbol in content


def test_demo_captain_script_runs_and_prints_final_proof(capsys):
    exit_code = demo_captain_mode.main()
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "Captain Mode Demo Smoke" in captured
    assert "thread_id:" in captured
    assert "captain_run_id:" in captured
    assert "queue item count/statuses:" in captured
    assert "assignment count/statuses:" in captured
    assert "exported prompt identifiers/paths:" in captured
    assert "transition count:" in captured
    assert "evidence count:" in captured
    assert "continue results: blocked -> blocked; approved -> ready_to_continue" in captured
    assert "final Captain state/status: ready_to_continue" in captured
    assert "Captain Mode Demo Smoke Completed Successfully" in captured


def test_demo_captain_script_exports_text_only_prompts(capsys):
    exit_code = demo_captain_mode.main()
    captured = capsys.readouterr().out
    assert exit_code == 0
    export_root = demo_captain_mode.EXPORT_ROOT
    assert export_root.exists()
    exports = sorted(export_root.glob("*.txt"))
    assert exports, "Expected exported prompt text files in /tmp."
    for path in exports:
        content = path.read_text(encoding="utf-8")
        assert "Do not commit." in content
        assert "Do not push." in content
        assert "Do not launch real external agents." in content
    assert "exported prompt identifiers/paths:" in captured
