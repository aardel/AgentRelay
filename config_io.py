"""Read and write AgentRelay settings in plain YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agentrelay import DEFAULT_CONFIG, Config


def load_raw(path: Path | None = None) -> dict[str, Any]:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def save_raw(data: dict[str, Any], path: Path | None = None) -> None:
    path = path or DEFAULT_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG
    return Config.load(path)


def update_settings(
    *,
    path: Path | None = None,
    node_name: str | None = None,
    trusted_peers: list[str] | None = None,
    wait_before_send_seconds: int | None = None,
    default_agent: str | None = None,
) -> Config:
    path = path or DEFAULT_CONFIG
    data = load_raw(path)
    if node_name is not None:
        data["node_name"] = node_name
    if default_agent is not None:
        data["default_agent"] = default_agent
    relay = data.setdefault("relay", {})
    if wait_before_send_seconds is not None:
        relay["wait_before_send_seconds"] = int(wait_before_send_seconds)
    if trusted_peers is not None:
        data["trusted_peers"] = list(trusted_peers)
    save_raw(data, path)
    return Config.load(path)
