"""
Store and retrieve agent resumes (markdown) and persistent memory (JSON).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

BASE_DIR = Path.home() / ".config" / "agentrelay"
RESUMES_DIR = BASE_DIR / "resumes"
MEMORY_DIR = BASE_DIR / "memory"


def _agent_filename(agent_id: str, suffix: str) -> str:
    agent = str(agent_id or "").strip()
    if not agent:
        raise ValueError("agent id is required")
    return f"{quote(agent, safe='._-')}.{suffix}"


class AgentDataStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or BASE_DIR
        self.resumes_dir = self.root / "resumes"
        self.memory_dir = self.root / "memory"
        self.resumes_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def get_resume(self, agent_id: str) -> str:
        path = self.resumes_dir / _agent_filename(agent_id, "md")
        if not path.exists():
            return f"# {agent_id.title()}\n\nNo resume yet. Tell this agent to write one!"
        return path.read_text(encoding="utf-8")

    def save_resume(self, agent_id: str, content: str) -> None:
        path = self.resumes_dir / _agent_filename(agent_id, "md")
        path.write_text(str(content or ""), encoding="utf-8")

    def get_memory(self, agent_id: str) -> dict[str, Any]:
        path = self.memory_dir / _agent_filename(agent_id, "json")
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save_memory(self, agent_id: str, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ValueError("memory must be a JSON object")
        path = self.memory_dir / _agent_filename(agent_id, "json")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def update_memory(self, agent_id: str, key: str, value: Any) -> None:
        mem = self.get_memory(agent_id)
        mem[key] = value
        self.save_memory(agent_id, mem)

    def list_resumes(self) -> list[str]:
        return [unquote(p.stem) for p in self.resumes_dir.glob("*.md")]
