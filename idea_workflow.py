"""Prompt builders and concept compilation for the Ideas workflow."""
from __future__ import annotations

from typing import Any


def brainstorm_prompt(idea: dict, user_message: str) -> str:
    title = idea.get("title", "Untitled")
    desc = (idea.get("description") or "").strip()
    notes = (idea.get("notes") or "").strip()
    prior = _format_findings_brief(idea.get("findings") or [])
    parts = [
        f"[AgentRelay Idea brainstorm — {title}]",
        "",
        "Help explore and analyze this idea. Focus on feasibility, risks, "
        "architecture options, and a practical implementation approach.",
    ]
    if desc:
        parts.extend(["", "Description:", desc])
    if notes:
        parts.extend(["", "Notes:", notes])
    if prior:
        parts.extend(["", "Prior findings:", prior])
    parts.extend(["", "Question / request:", user_message.strip()])
    return "\n".join(parts)


def build_concept_document(idea: dict) -> str:
    title = idea.get("title", "Untitled")
    desc = (idea.get("description") or "").strip()
    notes = (idea.get("notes") or "").strip()
    findings = idea.get("findings") or []
    parts = [
        f"# Concept: {title}",
        "",
        f"Priority: {idea.get('priority', 'medium')}",
    ]
    if desc:
        parts.extend(["", "## Summary", desc])
    if findings:
        parts.append("")
        parts.append("## Research & analysis")
        for i, f in enumerate(findings, 1):
            agent = f.get("agent") or "unknown"
            ts = f.get("ts", 0)
            header = f"### Finding {i} ({agent})"
            if ts:
                from datetime import UTC, datetime
                header += (
                    f" — {datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%d %H:%M')} UTC"
                )
            parts.append(header)
            if f.get("prompt"):
                parts.append(f"**Prompt:** {f['prompt']}")
            parts.append(f.get("content", "").strip())
            parts.append("")
    if notes:
        parts.extend(["", "## Additional notes", notes])
    parts.extend([
        "",
        "## Execution checklist",
        "- [ ] Confirm scope and acceptance criteria",
        "- [ ] Identify files/modules to change",
        "- [ ] Implement core change",
        "- [ ] Test and verify",
    ])
    return "\n".join(parts).strip()


def concept_discussion_prompt(idea: dict, *, round_note: str = "") -> str:
    concept = (idea.get("concept") or "").strip()
    if not concept:
        concept = build_concept_document(idea)
    title = idea.get("title", "Untitled")
    prior = _format_discussions_brief(idea.get("concept_discussions") or [])
    parts = [
        f"[AgentRelay Concept — {title}]",
        "",
        "A concept is ready for team review. Read it carefully, then share "
        "concerns, alternatives, and suggestions. Be specific and actionable.",
        "",
        "---",
        concept,
        "---",
    ]
    if prior:
        parts.extend(["", "Discussion so far:", prior])
    if round_note:
        parts.extend(["", round_note])
    parts.append("")
    parts.append(
        "Reply with: (1) summary of your view, (2) risks or gaps, "
        "(3) recommended next steps."
    )
    return "\n".join(parts)


def execution_prompt(idea: dict) -> str:
    concept = (idea.get("concept") or "").strip()
    if concept and idea.get("concept_published_at"):
        return (
            f"[AgentRelay Idea — execute concept: {idea.get('title', 'Untitled')}]\n\n"
            f"{concept}\n\n"
            "Implement this concept. Use the checklist and prior discussion "
            "as guidance. Ask if anything is ambiguous before large changes."
        )
    return ""


def _format_findings_brief(findings: list[dict]) -> str:
    if not findings:
        return ""
    lines = []
    for f in findings[-5:]:
        agent = f.get("agent") or "?"
        snippet = (f.get("content") or "")[:400]
        lines.append(f"- [{agent}] {snippet}")
    return "\n".join(lines)


def _format_discussions_brief(discussions: list[dict]) -> str:
    if not discussions:
        return ""
    lines = []
    for d in discussions[-8:]:
        agent = d.get("agent") or "?"
        snippet = (d.get("content") or "")[:300]
        lines.append(f"- {agent}: {snippet}")
    return "\n".join(lines)
