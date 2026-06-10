"""Run review reports for operator export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .proof_gates import list_gates_for_run
from .run_history import evidence_summaries_for_run, get_run_record, redact_secrets


def _section(title: str, body: str) -> str:
    text = (body or "").strip()
    if not text:
        text = "(none)"
    return f"## {title}\n\n{text}\n"


def build_run_report_markdown(
    root: Path,
    run_id: str,
    *,
    run: dict[str, Any] | None = None,
) -> str:
    record = run or get_run_record(root, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    evidence = evidence_summaries_for_run(root, list(record.get("evidence_ids") or []))
    gates = list_gates_for_run(root, run_id)
    prompt = str(record.get("prompt") or record.get("prompt_excerpt") or "")
    transcript = str(record.get("transcript_excerpt") or "")
    prompt, _ = redact_secrets(prompt)
    transcript, _ = redact_secrets(transcript)
    lines = [
        f"# Warden Run Report: {record.get('title') or run_id}",
        "",
        f"- Run ID: `{run_id}`",
        f"- Agent: `{record.get('agent_id') or 'unknown'}`",
        f"- Status: `{record.get('status') or 'unknown'}`",
        f"- Started: {record.get('started_at') or '—'}",
        f"- Completed: {record.get('completed_at') or '—'}",
    ]
    if record.get("plan_id"):
        lines.append(f"- Plan ID: `{record['plan_id']}`")
    lines.append("")
    lines.append(_section("Prompt excerpt", prompt))
    lines.append(_section("Transcript excerpt", transcript))
    if evidence:
        lines.append("## Evidence\n")
        for item in evidence:
            summary, _ = redact_secrets(str(item.get("summary") or item.get("content_excerpt") or ""))
            lines.append(f"- **{item.get('title')}** ({item.get('type')}) — {summary}")
        lines.append("")
    else:
        lines.append(_section("Evidence", "(none linked)"))
    if gates:
        lines.append("## Proof gate decisions\n")
        for gate in gates:
            reason, _ = redact_secrets(str(gate.get("decision_reason") or gate.get("summary") or ""))
            lines.append(
                f"- **{gate.get('title')}** — `{gate.get('status')}`"
                + (f" — {reason}" if reason else "")
            )
        lines.append("")
    else:
        lines.append(_section("Proof gate decisions", "(none)"))
    return "\n".join(lines).strip() + "\n"


def build_run_report_payload(root: Path, run_id: str) -> dict[str, Any]:
    run = get_run_record(root, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    evidence = evidence_summaries_for_run(root, list(run.get("evidence_ids") or []))
    gates = list_gates_for_run(root, run_id)
    markdown = build_run_report_markdown(root, run_id, run=run)
    return {
        "service": "mcharness-control-plane",
        "run_id": run_id,
        "format": "markdown",
        "markdown": markdown,
        "run": run,
        "evidence": evidence,
        "gates": gates,
        "redacted": bool(run.get("redacted")),
    }