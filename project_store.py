"""Loaded project workspaces — registry and active project for agent cwd."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    return Path.home() / ".config" / "agentrelay"


def _normalize_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def path_under_project(child: str | Path, project_root: str | Path) -> bool:
    """True if *child* is the project root or a path inside it."""
    try:
        root = _normalize_path(project_root)
        other = _normalize_path(child)
    except (OSError, ValueError):
        return False
    if other == root:
        return True
    try:
        other.relative_to(root)
        return True
    except ValueError:
        return False


class ProjectStore:
    """Persists recent projects and the active workspace path."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_config_dir() / "projects.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"active_id": None, "projects": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"active_id": None, "projects": []}
        if not isinstance(data, dict):
            return {"active_id": None, "projects": []}
        data.setdefault("active_id", None)
        data.setdefault("projects", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_projects(self) -> list[dict[str, Any]]:
        data = self._load()
        projects = sorted(
            data.get("projects") or [],
            key=lambda p: p.get("last_opened") or 0,
            reverse=True,
        )
        out: list[dict[str, Any]] = []
        for p in projects:
            path = p.get("local_path") or ""
            if path and Path(path).is_dir():
                out.append(dict(p))
        return out

    def get(self, project_id: str) -> dict | None:
        for p in self.list_projects():
            if p.get("id") == project_id:
                return p
        return None

    def register(self, local_path: str | Path, name: str | None = None) -> dict:
        root = _normalize_path(local_path)
        if not root.is_dir():
            raise ValueError(f"Not a folder: {root}")

        data = self._load()
        projects: list[dict] = data.get("projects") or []
        root_s = str(root)
        now = time.time()

        for p in projects:
            if p.get("local_path") == root_s:
                p["last_opened"] = now
                if name:
                    p["name"] = name.strip()
                self._save(data)
                return dict(p)

        entry = {
            "id": uuid.uuid4().hex[:12],
            "name": (name or root.name).strip() or root.name,
            "local_path": root_s,
            "last_opened": now,
            "created_at": now,
        }
        projects.append(entry)
        data["projects"] = projects
        self._save(data)
        return entry

    def set_active(self, project_id: str | None) -> dict | None:
        data = self._load()
        if not project_id:
            data["active_id"] = None
            self._save(data)
            return None
        project = self.get(project_id)
        if not project:
            return None
        data["active_id"] = project_id
        project["last_opened"] = time.time()
        self._save(data)
        return project

    def set_active_path(self, local_path: str | Path) -> dict:
        project = self.register(local_path)
        self.set_active(project["id"])
        return project

    def get_active(self) -> dict | None:
        data = self._load()
        active_id = data.get("active_id")
        if not active_id:
            return None
        project = self.get(active_id)
        if not project:
            data["active_id"] = None
            self._save(data)
            return None
        return project

    def active_path(self) -> Path | None:
        project = self.get_active()
        if not project:
            return None
        path = Path(project["local_path"])
        return path if path.is_dir() else None

    def remove(self, project_id: str) -> bool:
        data = self._load()
        projects = data.get("projects") or []
        filtered = [p for p in projects if p.get("id") != project_id]
        if len(filtered) == len(projects):
            return False
        if data.get("active_id") == project_id:
            data["active_id"] = None
        data["projects"] = filtered
        self._save(data)
        return True
