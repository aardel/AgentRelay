"""Persistent storage for the Ideas feature (ideas.json)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from idea_workflow import build_concept_document

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
_VALID_PRIORITIES = frozenset(_PRIORITY_RANK)
_VALID_STATUSES = frozenset({
    "draft", "exploring", "ready", "concept",
    "queued", "in_progress", "done",
})
_EDITABLE = {
    "title", "description", "priority", "status", "assigned_agent",
    "linked_task_ids", "notes", "brainstorm_agent", "concept", "thread_id",
}


def _normalize(idea: dict) -> dict:
    idea.setdefault("brainstorm_agent", None)
    idea.setdefault("findings", [])
    idea.setdefault("concept", "")
    idea.setdefault("concept_published_at", None)
    idea.setdefault("concept_discussions", [])
    idea.setdefault("thread_id", None)
    idea.setdefault("updated_at", idea.get("created_at", time.time()))
    return idea


class IdeaStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path.home() / ".config" / "agentrelay" / "ideas.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else []
            return [_normalize(i) for i in items]
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
                return _normalize(dict(idea))
        return None

    def create(self, title: str, description: str = "", priority: str = "medium") -> dict:
        idea: dict[str, Any] = _normalize({
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "description": description.strip(),
            "priority": priority if priority in _VALID_PRIORITIES else "medium",
            "status": "draft",
            "assigned_agent": None,
            "linked_task_ids": [],
            "created_at": time.time(),
            "updated_at": time.time(),
            "notes": "",
        })
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
                idea["updated_at"] = time.time()
                self._save(ideas)
                return _normalize(dict(idea))
        return None

    def delete(self, idea_id: str) -> bool:
        ideas = self._load()
        filtered = [i for i in ideas if i.get("id") != idea_id]
        if len(filtered) == len(ideas):
            return False
        self._save(filtered)
        return True

    def add_finding(
        self,
        idea_id: str,
        *,
        agent: str,
        content: str,
        prompt: str = "",
        source: str = "agent",
    ) -> dict | None:
        ideas = self._load()
        for idea in ideas:
            if idea.get("id") != idea_id:
                continue
            entry = {
                "id": uuid.uuid4().hex,
                "ts": time.time(),
                "agent": agent,
                "source": source,
                "prompt": prompt.strip(),
                "content": content.strip(),
            }
            idea.setdefault("findings", []).append(entry)
            if idea.get("status") == "draft":
                idea["status"] = "exploring"
            idea["updated_at"] = time.time()
            self._save(ideas)
            return _normalize(dict(idea))
        return None

    def remove_finding(self, idea_id: str, finding_id: str) -> dict | None:
        ideas = self._load()
        for idea in ideas:
            if idea.get("id") != idea_id:
                continue
            findings = idea.get("findings") or []
            filtered = [f for f in findings if f.get("id") != finding_id]
            if len(filtered) == len(findings):
                return None
            idea["findings"] = filtered
            idea["updated_at"] = time.time()
            self._save(ideas)
            return _normalize(dict(idea))
        return None

    def compile_concept(self, idea_id: str) -> dict | None:
        idea = self.get(idea_id)
        if not idea:
            return None
        concept = build_concept_document(idea)
        return self.update(idea_id, concept=concept, status="ready")

    def publish_concept(self, idea_id: str) -> dict | None:
        idea = self.get(idea_id)
        if not idea:
            return None
        concept = (idea.get("concept") or "").strip()
        if not concept:
            idea = self.compile_concept(idea_id)
            if not idea:
                return None
            concept = idea.get("concept", "")
        now = time.time()
        ideas = self._load()
        for item in ideas:
            if item.get("id") == idea_id:
                item["concept"] = concept
                item["concept_published_at"] = now
                item["status"] = "concept"
                item["updated_at"] = now
                self._save(ideas)
                return _normalize(dict(item))
        return None

    def add_discussion(
        self,
        idea_id: str,
        *,
        agent: str,
        content: str,
        source: str = "agent",
    ) -> dict | None:
        ideas = self._load()
        for idea in ideas:
            if idea.get("id") != idea_id:
                continue
            entry = {
                "id": uuid.uuid4().hex,
                "ts": time.time(),
                "agent": agent,
                "source": source,
                "content": content.strip(),
            }
            idea.setdefault("concept_discussions", []).append(entry)
            idea["updated_at"] = time.time()
            self._save(ideas)
            return _normalize(dict(idea))
        return None
