"""
Optional bridge to a local agentmemory server (https://github.com/rohitg00/agentmemory).

AgentRelay keeps relay-specific resume/memory in agent_data.py. This module adds
semantic recall on terminal launch and optional session observation on PTY close
when a sidecar agentmemory instance is running.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import aiohttp

log = logging.getLogger("agentrelay.agentmemory")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_OBSERVE_MAX_CHARS = 12_000


@dataclass
class AgentmemoryConfig:
    enabled: bool = False
    url: str = "http://127.0.0.1:3111"
    secret: str = ""
    project: str = "agentrelay"
    token_budget: int = 1500
    inject_on_launch: bool = True
    observe_on_close: bool = True
    timeout_seconds: float = 3.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AgentmemoryConfig":
        raw = data or {}
        return cls(
            enabled=bool(raw.get("enabled", False)),
            url=str(raw.get("url") or "http://127.0.0.1:3111").rstrip("/"),
            secret=str(raw.get("secret") or os.environ.get("AGENTMEMORY_SECRET", "")),
            project=str(raw.get("project") or "agentrelay"),
            token_budget=max(200, int(raw.get("token_budget") or 1500)),
            inject_on_launch=bool(raw.get("inject_on_launch", True)),
            observe_on_close=bool(raw.get("observe_on_close", True)),
            timeout_seconds=max(0.5, float(raw.get("timeout_seconds") or 3.0)),
        )


def _headers(cfg: AgentmemoryConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if cfg.secret:
        headers["Authorization"] = f"Bearer {cfg.secret}"
    return headers


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _extract_result_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("content", "text", "narrative", "summary", "observation", "body"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def format_recall_markdown(results: list[Any], *, token_budget: int) -> str:
    """Turn smart-search hits into a compact markdown block for snippet injection."""
    lines: list[str] = []
    approx_chars = 0
    char_budget = max(400, token_budget * 4)
    for item in results:
        text = _extract_result_text(item)
        if not text:
            continue
        chunk = _truncate(text, 600)
        if approx_chars + len(chunk) > char_budget:
            break
        lines.append(f"- {chunk}")
        approx_chars += len(chunk)
    if not lines:
        return ""
    return "## Project memory (agentmemory)\n\n" + "\n".join(lines) + "\n\n---\n\n"


async def health_ok(cfg: AgentmemoryConfig) -> bool:
    if not cfg.enabled:
        return False
    url = f"{cfg.url}/agentmemory/health"
    timeout = aiohttp.ClientTimeout(total=cfg.timeout_seconds)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=_headers(cfg)) as resp:
                return resp.status == 200
    except Exception as exc:
        log.debug("agentmemory health check failed: %s", exc)
        return False


async def fetch_recall_context(
    cfg: AgentmemoryConfig,
    *,
    query: str,
    agent_id: str | None = None,
) -> str:
    """Hybrid-search agentmemory and return markdown for snippet injection."""
    if not cfg.enabled or not cfg.inject_on_launch:
        return ""
    query = (query or "").strip()
    if not query:
        query = f"AgentRelay agent {agent_id or 'session'} context preferences"
    payload = {
        "project": cfg.project,
        "query": query,
        "token_budget": cfg.token_budget,
    }
    url = f"{cfg.url}/agentmemory/smart-search"
    timeout = aiohttp.ClientTimeout(total=cfg.timeout_seconds)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=_headers(cfg)) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    log.debug("agentmemory smart-search %s: %s", resp.status, body[:200])
                    return ""
                data = await resp.json(content_type=None)
    except Exception as exc:
        log.debug("agentmemory smart-search failed: %s", exc)
        return ""

    results: list[Any] = []
    if isinstance(data, dict):
        raw = data.get("results") or data.get("memories") or data.get("hits")
        if isinstance(raw, list):
            results = raw
        elif isinstance(data.get("context"), str):
            return _truncate(
                "## Project memory (agentmemory)\n\n"
                + data["context"].strip()
                + "\n\n---\n\n",
                cfg.token_budget * 4,
            )
    return format_recall_markdown(results, token_budget=cfg.token_budget)


async def observe_session_end(
    cfg: AgentmemoryConfig,
    *,
    agent_id: str,
    session_id: str,
    reason: str,
    scrollback: bytes,
    node_name: str,
    uptime_seconds: float,
) -> None:
    """Send a terminal session summary to agentmemory (best-effort)."""
    if not cfg.enabled or not cfg.observe_on_close:
        return
    plain = strip_ansi(
        scrollback.decode("utf-8", errors="replace") if scrollback else ""
    )
    tail = _truncate(plain, _OBSERVE_MAX_CHARS)
    summary = (
        f"AgentRelay PTY session ended ({reason}).\n"
        f"Node: {node_name}\n"
        f"Agent: {agent_id}\n"
        f"Session: {session_id}\n"
        f"Uptime: {uptime_seconds:.0f}s\n\n"
        f"Terminal output (tail):\n{tail}"
    )
    payload = {
        "project": cfg.project,
        "content": summary,
        "session_id": session_id,
        "metadata": {
            "source": "agentrelay",
            "agent": agent_id,
            "node": node_name,
            "reason": reason,
        },
    }
    url = f"{cfg.url}/agentmemory/observe"
    timeout = aiohttp.ClientTimeout(total=cfg.timeout_seconds)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=_headers(cfg)) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    log.debug("agentmemory observe %s: %s", resp.status, body[:200])
    except Exception as exc:
        log.debug("agentmemory observe failed: %s", exc)
