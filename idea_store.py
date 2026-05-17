"""Persistent storage for the Ideas feature (ideas.json)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
_VALID_PRIORITIES = frozenset(_PRIORITY_RANK)
_VALID_STATUSES = frozenset({"draft", "queued", "in_progress", "done"})
_EDITABLE = {"title", "description", "priority", "status", "assigned_agent", "linked_task_ids", "notes"}


class IdeaStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path.home() / ".config" / "agentrelay" / "ideas.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, ideas: list[dict]) -> None:
        self._path.write_text(json.dumps(ideas, indent=2), encoding="utf-8")

    def list_all(self) -> list[dict]:
        ideas = self._load()
        ideas.sort(key=lambda x: (
            _PRIORITY_RANK.get(x.get("priority", "low"), 2),
            x.get("created_at", 0),
        ))
        return ideas

    def get(self, idea_id: str) -> dict | None:
        for idea in self._load():
            if idea.get("id") == idea_id:
                return idea
        return None

    def create(self, title: str, description: str = "", priority: str = "medium") -> dict:
        idea: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "description": description.strip(),
            "priority": priority if priority in _VALID_PRIORITIES else "medium",
            "status": "draft",
            "assigned_agent": None,
            "linked_task_ids": [],
            "created_at": time.time(),
            "notes": "",
        }
        ideas = self._load()
        ideas.append(idea)
        self._save(ideas)
        return idea

    def update(self, idea_id: str, **kwargs: Any) -> dict | None:
        ideas = self._load()
        for idea in ideas:
            if idea.get("id") == idea_id:
                for k, v in kwargs.items():
                    if k not in _EDITABLE:
                        continue
                    if k == "priority" and v not in _VALID_PRIORITIES:
                        continue
                    if k == "status" and v not in _VALID_STATUSES:
                        continue
                    idea[k] = v
                self._save(ideas)
                return idea
        return None

    def delete(self, idea_id: str) -> bool:
        ideas = self._load()
        filtered = [i for i in ideas if i.get("id") != idea_id]
        if len(filtered) == len(ideas):
            return False
        self._save(filtered)
        return True
