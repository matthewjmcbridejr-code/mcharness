from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

from src.marius_desktop.api import get_status
from src.marius_desktop.captain import CAPTAIN_ROOT
from src.marius_desktop.captain import (
    CaptainAssignmentCompleteRequest,
    CaptainAssignmentEvidenceRequest,
    CaptainPlanRequest,
    CaptainQueueItemCreateRequest,
    add_captain_queue_item,
    assign_captain_minions,
    complete_captain_assignment,
    continue_captain_run,
    create_captain_state_machine_run,
    export_captain_queue_item,
    get_captain_run,
    get_captain_transitions,
    plan_captain_run,
    queue_captain_run,
    record_captain_assignment_evidence,
)
from src.marius_desktop.workbench import (
    STORE as WORKBENCH_STORE,
    WorkbenchThreadCreateRequest,
    create_thread,
)
from src.marius_desktop.workbench import WORKBENCH_ROOT


DEMO_ROOT = Path("/tmp/mcharness-captain-mode-demo")
EXPORT_ROOT = DEMO_ROOT / "exports"
DEMO_THREAD_ID = "captain_demo_thread"
DEMO_THREAD_TITLE = "Captain Demo Thread"
DEMO_THREAD_GOAL = "Prove the Captain Mode flow through the local API."
DEMO_PLAN_INSTRUCTION = "Create a deterministic supervised plan with bounded minions, evidence, and proof gates."


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _cleanup_runtime_state() -> None:
    for directory in [WORKBENCH_ROOT, CAPTAIN_ROOT]:
        if directory.exists():
            shutil.rmtree(directory)
    if EXPORT_ROOT.exists():
        shutil.rmtree(EXPORT_ROOT)
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)


def _cleanup_captain_runtime_only() -> None:
    for directory in [WORKBENCH_ROOT, CAPTAIN_ROOT]:
        if directory.exists():
            shutil.rmtree(directory)


def _queue_statuses(queue_items: list[dict[str, object]]) -> str:
    return ", ".join(f"{item.get('queue_item_id') or item.get('title')}:{item.get('status')}" for item in queue_items)


def _assignment_statuses(assignments: list[dict[str, object]]) -> str:
    return ", ".join(f"{item.get('assignment_id') or item.get('title')}:{item.get('status')}" for item in assignments)


def main() -> int:
    print("=== Captain Mode Demo Smoke ===")
    _cleanup_runtime_state()

    try:
        service_status = get_status()
        _assert(service_status.get("status") == "online", "Expected local McHarness API to be online.")

        thread = create_thread(
            WorkbenchThreadCreateRequest(
                thread_id=DEMO_THREAD_ID,
                title=DEMO_THREAD_TITLE,
                goal=DEMO_THREAD_GOAL,
            )
        )
        thread_id = thread["thread_id"]
        _assert(thread_id == DEMO_THREAD_ID, f"Expected deterministic thread id {DEMO_THREAD_ID}, got {thread_id}.")

        captain = create_captain_state_machine_run(thread_id, DEMO_THREAD_GOAL).model_dump(mode="json")
        captain_run_id = captain["captain_run_id"]

        captain = plan_captain_run(captain_run_id, CaptainPlanRequest(instruction=DEMO_PLAN_INSTRUCTION)).model_dump(mode="json")
        captain = queue_captain_run(captain_run_id).model_dump(mode="json")
        _assert(len(captain["prompt_queue"]) >= 3, "Captain queue generation should produce at least three queue items.")

        captain = add_captain_queue_item(
            captain_run_id,
            CaptainQueueItemCreateRequest(
                title="Validate exported prompt text",
                prompt="Export the minion prompt and confirm it is text only.",
                target_role="reviewer",
                file_scope=[
                    "web/mctable-studio/cockpit.html",
                    "tests/test_marius_desktop_cockpit_static.py",
                ],
                forbidden_file_scope=[
                    "_mctable/**",
                    "src-tauri/**",
                ],
                evidence_required=[
                    "Export prompt visible.",
                    "No launch buttons present.",
                ],
                acceptance_checks=[
                    "Prompt export is text only.",
                    "No arbitrary shell execution.",
                ],
                export_format="codex_cli",
            ),
        ).model_dump(mode="json")

        captain = assign_captain_minions(captain_run_id).model_dump(mode="json")
        assignments = list(captain.get("assignments") or [])
        queue_items = list(captain.get("prompt_queue") or [])
        _assert(assignments, "Expected at least one minion assignment.")
        _assert(queue_items, "Expected a non-empty prompt queue.")

        exported_prompts: list[tuple[str, str]] = []
        for item in queue_items:
            queue_item_id = item["queue_item_id"]
            exported = export_captain_queue_item(queue_item_id)
            export_path = EXPORT_ROOT / f"{queue_item_id}.txt"
            export_path.write_text(exported, encoding="utf-8")
            exported_prompts.append((queue_item_id, str(export_path)))
            _assert("Do not commit." in exported, f"Export for {queue_item_id} is missing safety text.")
            _assert("Do not push." in exported, f"Export for {queue_item_id} is missing push prohibition.")
            _assert("Do not launch real external agents." in exported, f"Export for {queue_item_id} is missing launch prohibition.")

        first_assignment = assignments[0]
        first_assignment_id = first_assignment["assignment_id"]
        first_assignment_status = first_assignment["status"]
        _assert(first_assignment_status in {"assigned", "waiting_for_result"}, "First assignment should be actionable.")

        captain = record_captain_assignment_evidence(
            captain_run_id,
            first_assignment_id,
            CaptainAssignmentEvidenceRequest(
                evidence_summary="Deterministic demo evidence recorded locally.",
                source_ref="scripts/demo_captain_mode.py",
                artifact_refs=[str(EXPORT_ROOT / f"{queue_items[0]['queue_item_id']}.txt")],
                verdict="passed",
            ),
        ).model_dump(mode="json")

        captain = complete_captain_assignment(
            captain_run_id,
            first_assignment_id,
            CaptainAssignmentCompleteRequest(
                evidence_summary="Deterministic demo assignment completed with evidence.",
                output_summary="Local-only review completed.",
            ),
        ).model_dump(mode="json")

        blocked_continue = continue_captain_run(captain_run_id)
        _assert(blocked_continue["status"] == "blocked", "Expected continuation to be blocked while the proof gate is open.")

        gate_id = captain.get("proof_gate_id")
        _assert(gate_id, "Captain run should expose a proof_gate_id.")
        WORKBENCH_STORE.decide_run_proof_gate(
            gate_id,
            SimpleNamespace(
                decision="approved",
                actor="operator",
                note="Approved for the deterministic Captain smoke demo.",
            ),
        )

        ready_continue = continue_captain_run(captain_run_id)
        _assert(ready_continue["status"] == "ready_to_continue", "Expected continuation to become ready_to_continue after gate approval.")

        captain_run = get_captain_run(captain_run_id)
        transitions = get_captain_transitions(captain_run_id)
        workbench_run = WORKBENCH_STORE.get_run(captain_run_id).model_dump(mode="json")

        queue_items_final = list(captain_run.get("prompt_queue") or [])
        assignments_final = list(captain_run.get("assignments") or [])
        queue_statuses = _queue_statuses(queue_items_final)
        assignment_statuses = _assignment_statuses(assignments_final)
        evidence_count = len(workbench_run.get("evidence_records") or [])
        transition_count = len(transitions)

        _assert(queue_items_final, "Final Captain run should include queue items.")
        _assert(assignments_final, "Final Captain run should include assignments.")
        _assert(transition_count > 0, "Expected Captain transitions to be recorded.")
        _assert(evidence_count > 0, "Expected evidence records in the linked workbench run.")
        _assert(captain_run.get("status") == "ready_to_continue", "Expected final Captain state to be ready_to_continue.")
        _assert(any(item["status"] == "completed" for item in assignments_final), "At least one assignment should be completed.")

        print("\nDemo proof summary:")
        print(f"- thread_id: {thread_id}")
        print(f"- captain_run_id: {captain_run_id}")
        print(f"- queue item count/statuses: {len(queue_items_final)} [{queue_statuses}]")
        print(f"- assignment count/statuses: {len(assignments_final)} [{assignment_statuses}]")
        print(f"- exported prompt identifiers/paths: {exported_prompts}")
        print(f"- transition count: {transition_count}")
        print(f"- evidence count: {evidence_count}")
        print(f"- continue results: blocked -> {blocked_continue['status']}; approved -> {ready_continue['status']}")
        print(f"- final Captain state/status: {captain_run.get('status')}")
        print("=== Captain Mode Demo Smoke Completed Successfully ===")

        return 0
    finally:
        _cleanup_captain_runtime_only()


if __name__ == "__main__":
    raise SystemExit(main())
