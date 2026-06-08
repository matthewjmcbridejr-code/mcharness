from pathlib import Path

from scripts import demo_marius_desktop


SCRIPT = Path("scripts/demo_marius_desktop.py")


def test_demo_script_imports():
    assert hasattr(demo_marius_desktop, "main")


def test_demo_script_has_no_shell_true():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in content


def test_demo_script_references_fake_worker_commands_only():
    content = SCRIPT.read_text(encoding="utf-8")
    for command in ["fake-worker-success", "fake-worker-fail", "fake-worker-sleep"]:
        assert command in content
    for blocked in ["grok-build-stub", "codex-stub", "agy", "rm -rf /"]:
        if blocked != "rm -rf /":
            assert blocked not in content


def test_demo_script_exercises_captain_mode_if_available(capsys):
    exit_code = demo_marius_desktop.main()
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "Captain run created:" in captured
    assert "Captain next action blocked by hard gate: yes" in captured
    assert "Command execution request blocked/not_implemented: yes" in captured


def test_demo_script_rejects_unknown_command(capsys):
    exit_code = demo_marius_desktop.main()
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "Unknown command rejected through API: yes" in captured
