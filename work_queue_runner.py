"""Auto-run queued ideas and bugs when no agent terminals are active."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from idea_store import IdeaStore
from bug_store import BugStore

if TYPE_CHECKING:
    from agentrelay import AgentRelay

log = logging.getLogger("agentrelay.work_queue")

_IDEA_RANK = {"high": 0, "medium": 1, "low": 2}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_work_sessions: dict[str, tuple[str, str]] = {}


def build_work_prompt(kind: str, item: dict) -> str:
    title = item.get("title", "Untitled")
    desc = (item.get("description") or "").strip()
    notes = (item.get("notes") or "").strip()
    if kind == "bug":
        severity = item.get("severity", "medium")
        steps = (item.get("steps_to_reproduce") or "").strip()
        parts = [
            f"[AgentRelay Bug — {title}]",
            "",
            f"Severity: {severity}",
        ]
        if desc:
            parts.extend(["", desc])
        if steps:
            parts.extend(["", "Steps to reproduce:", steps])
        if notes:
            parts.extend(["", f"Notes: {notes}"])
        parts.extend([
            "",
            "Please investigate, reproduce if needed, and fix this bug.",
        ])
        return "\n".join(parts)
    from idea_workflow import execution_prompt

    exec_prompt = execution_prompt(item)
    if exec_prompt:
        return exec_prompt
    priority = item.get("priority", "medium")
    parts = [
        f"[AgentRelay Idea — {title}]",
        "",
        f"Priority: {priority}",
    ]
    if desc:
        parts.extend(["", desc])
    if notes:
        parts.extend(["", f"Notes: {notes}"])
    parts.extend([
        "",
        "Please implement or explore this idea.",
    ])
    return "\n".join(parts)


def _queued_items(idea_store: IdeaStore, bug_store: BugStore) -> list[tuple[str, dict, int]]:
    items: list[tuple[str, dict, int]] = []
    for idea in idea_store.list_all():
        if idea.get("status") == "queued":
            rank = _IDEA_RANK.get(idea.get("priority", "low"), 2)
            items.append(("idea", idea, rank))
    for bug in bug_store.list_all():
        if bug.get("status") == "queued":
            rank = _SEVERITY_RANK.get(bug.get("severity", "low"), 3)
            items.append(("bug", bug, rank))
    items.sort(key=lambda x: (x[2], x[1].get("created_at", 0)))
    return items


def _store_for_kind(relay: "AgentRelay", kind: str):
    return relay.idea_store if kind == "idea" else relay.bug_store


def register_work_session(session_id: str, kind: str, item_id: str) -> None:
    _work_sessions[session_id] = (kind, item_id)


def bind_work_session(relay: "AgentRelay", session_id: str, kind: str, item_id: str) -> bool:
    """Link a PTY session to a work item; mark done when the session closes."""
    from agentrelay import pty_registry

    session = pty_registry.get(session_id)
    if not session:
        return False
    store = _store_for_kind(relay, kind)
    item = store.get(item_id)
    if not item or item.get("status") != "in_progress":
        return False
    register_work_session(session_id, kind, item_id)

    def _hook(sid: str, reason: str) -> None:
        asyncio.ensure_future(_on_work_session_closed(relay, sid, reason))

    session.chain_on_close(_hook)
    return True


async def _on_work_session_closed(
    relay: "AgentRelay", session_id: str, reason: str,
) -> None:
    entry = _work_sessions.pop(session_id, None)
    if not entry:
        return
    kind, item_id = entry
    store = _store_for_kind(relay, kind)
    item = store.get(item_id)
    if item and item.get("status") == "in_progress":
        store.update(item_id, status="done")
        log.info("work queue: marked %s %s done (session closed: %s)",
                 kind, item_id, reason)


async def try_dispatch_next(relay: "AgentRelay") -> dict[str, Any]:
    """Dispatch the highest-priority queued idea or bug when agents are idle."""
    from agentrelay import (
        _deliver_prompt_to_pty,
        _find_pty_for_adapter,
        list_active_agent_names,
    )

    if list_active_agent_names():
        return {"idle": False, "dispatched": False}

    queued = _queued_items(relay.idea_store, relay.bug_store)
    if not queued:
        return {"idle": True, "dispatched": False}

    kind, item, _rank = queued[0]
    store = _store_for_kind(relay, kind)
    item_id = item["id"]
    store.update(item_id, status="in_progress")

    agent = item.get("assigned_agent") or relay.cfg.default_agent
    if not agent:
        store.update(item_id, status="queued")
        return {
            "idle": True,
            "dispatched": False,
            "error": "no default_agent configured",
        }

    resolved = relay.cfg.resolve_adapter_name(agent, prefer_interactive=True)
    prompt = build_work_prompt(kind, item)
    wait = relay.cfg.wait_before_send_seconds

    if await _deliver_prompt_to_pty(resolved, prompt, wait):
        session = _find_pty_for_adapter(resolved)
        if session:
            bind_work_session(relay, session.session_id, kind, item_id)
        return {
            "idle": True,
            "dispatched": True,
            "kind": kind,
            "id": item_id,
            "agent": resolved,
            "delivered": True,
        }

    return {
        "idle": True,
        "dispatched": True,
        "kind": kind,
        "id": item_id,
        "agent": resolved,
        "prompt": prompt,
        "wait_seconds": wait,
        "needs_terminal": True,
    }
