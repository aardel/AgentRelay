"""
Agent-to-agent conversation threads for AgentRelay.

Each thread is a persisted dialogue between agents on different machines
(e.g. claude@desk-mac ↔ codex@test-bench).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

THREADS_DIR = Path.home() / ".config" / "agentrelay" / "threads"
MAX_HISTORY = 20


@dataclass
class TalkMessage:
    id: str
    thread_id: str
    ts: float
    from_node: str
    from_agent: str
    to_node: str
    to_agent: str
    role: str  # "user" | "assistant"
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TalkThread:
    id: str
    created: float
    updated: float
    peer_node: str
    local_agent: str
    remote_agent: str
    remote_node: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConversationStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or THREADS_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _thread_path(self, thread_id: str) -> Path:
        return self.root / f"{thread_id}.jsonl"

    def _meta_path(self) -> Path:
        return self.root / "index.json"

    def _load_meta(self) -> dict[str, Any]:
        path = self._meta_path()
        if not path.exists():
            return {"threads": {}}
        return json.loads(path.read_text())

    def _save_meta(self, meta: dict[str, Any]) -> None:
        self._meta_path().write_text(json.dumps(meta, indent=2))

    def list_threads(self) -> list[dict[str, Any]]:
        meta = self._load_meta()
        threads = list(meta.get("threads", {}).values())
        threads.sort(key=lambda t: t.get("updated", 0), reverse=True)
        return threads

    def get_messages(self, thread_id: str) -> list[TalkMessage]:
        path = self._thread_path(thread_id)
        if not path.exists():
            return []
        messages: list[TalkMessage] = []
        for line in path.read_text().splitlines():
            if line.strip():
                messages.append(TalkMessage(**json.loads(line)))
        return messages

    def append(
        self,
        thread_id: str | None,
        *,
        local_node: str,
        peer_node: str,
        local_agent: str,
        remote_agent: str,
        remote_node: str | None = None,
        from_node: str,
        from_agent: str,
        to_node: str,
        to_agent: str,
        role: str,
        content: str,
    ) -> TalkMessage:
        meta = self._load_meta()
        threads: dict[str, Any] = meta.setdefault("threads", {})
        now = time.time()

        if not thread_id or thread_id not in threads:
            thread_id = uuid.uuid4().hex
            threads[thread_id] = TalkThread(
                id=thread_id,
                created=now,
                updated=now,
                peer_node=peer_node,
                local_agent=local_agent,
                remote_agent=remote_agent,
                remote_node=remote_node if remote_node else peer_node,
            ).to_dict()
        else:
            threads[thread_id]["updated"] = now

        msg = TalkMessage(
            id=uuid.uuid4().hex,
            thread_id=thread_id,
            ts=now,
            from_node=from_node,
            from_agent=from_agent,
            to_node=to_node,
            to_agent=to_agent,
            role=role,
            content=content,
        )
        with self._thread_path(thread_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg.to_dict()) + "\n")
        self._save_meta(meta)
        return msg

    def format_prompt(
        self,
        thread_id: str,
        *,
        local_node: str,
        from_node: str,
        from_agent: str,
        new_message: str,
        _messages: list["TalkMessage"] | None = None,
    ) -> str:
        history = (_messages if _messages is not None
                   else self.get_messages(thread_id))[-MAX_HISTORY:]
        lines = [
            "You are participating in an agent-to-agent conversation via AgentRelay.",
            f"A message arrived from {from_agent}@{from_node} (you are on {local_node}).",
            "",
            "Conversation so far:",
        ]
        if history:
            for m in history:
                who = f"{m.from_agent}@{m.from_node}"
                lines.append(f"[{who}]: {m.content}")
        else:
            lines.append("(no prior messages)")
        lines.extend([
            "",
            f"New message from {from_agent}@{from_node}:",
            new_message,
            "",
            "Reply directly to that agent. Be concise and actionable.",
        ])
        return "\n".join(lines)


def mirror_remote_turn(
    store: ConversationStore,
    thread_id: str | None,
    *,
    local_node: str,
    peer_node: str,
    local_agent: str,
    remote_agent: str,
    user_message: str,
    assistant_reply: str,
) -> str:
    """Record an outbound talk turn on the caller's machine."""
    user = store.append(
        thread_id,
        local_node=local_node,
        peer_node=peer_node,
        local_agent=local_agent,
        remote_agent=remote_agent,
        remote_node=peer_node,
        from_node=local_node,
        from_agent=local_agent,
        to_node=peer_node,
        to_agent=remote_agent,
        role="user",
        content=user_message,
    )
    store.append(
        user.thread_id,
        local_node=local_node,
        peer_node=peer_node,
        local_agent=local_agent,
        remote_agent=remote_agent,
        remote_node=peer_node,
        from_node=peer_node,
        from_agent=remote_agent,
        to_node=local_node,
        to_agent=local_agent,
        role="assistant",
        content=assistant_reply,
    )
    return user.thread_id
