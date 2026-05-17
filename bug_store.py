"""Persistent storage for the Bugs feature (bugs.json)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_VALID_SEVERITIES = frozenset(_SEVERITY_RANK)
_VALID_STATUSES = frozenset({"draft", "queued", "in_progress", "done"})
_EDITABLE = {
    "title", "description", "severity", "status",
    "assigned_agent", "linked_task_ids", "notes", "steps_to_reproduce",
}


class BugStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path.home() / ".config" / "agentrelay" / "bugs.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, bugs: list[dict]) -> None:
        self._path.write_text(json.dumps(bugs, indent=2), encoding="utf-8")

    def list_all(self) -> list[dict]:
        bugs = self._load()
        bugs.sort(key=lambda x: (
            _SEVERITY_RANK.get(x.get("severity", "low"), 3),
            x.get("created_at", 0),
        ))
        return bugs

    def get(self, bug_id: str) -> dict | None:
        for bug in self._load():
            if bug.get("id") == bug_id:
                return bug
        return None

    def create(
        self,
        title: str,
        description: str = "",
        severity: str = "medium",
        steps_to_reproduce: str = "",
    ) -> dict:
        bug: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "description": description.strip(),
            "steps_to_reproduce": steps_to_reproduce.strip(),
            "severity": severity if severity in _VALID_SEVERITIES else "medium",
            "status": "draft",
            "assigned_agent": None,
            "linked_task_ids": [],
            "created_at": time.time(),
            "notes": "",
        }
        bugs = self._load()
        bugs.append(bug)
        self._save(bugs)
        return bug

    def update(self, bug_id: str, **kwargs: Any) -> dict | None:
        bugs = self._load()
        for bug in bugs:
            if bug.get("id") == bug_id:
                for k, v in kwargs.items():
                    if k not in _EDITABLE:
                        continue
                    if k == "severity" and v not in _VALID_SEVERITIES:
                        continue
                    if k == "status" and v not in _VALID_STATUSES:
                        continue
                    bug[k] = v
                self._save(bugs)
                return bug
        return None

    def delete(self, bug_id: str) -> bool:
        bugs = self._load()
        filtered = [b for b in bugs if b.get("id") != bug_id]
        if len(filtered) == len(bugs):
            return False
        self._save(filtered)
        return True
