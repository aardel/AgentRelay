"""
PTYSession — platform-agnostic terminal session manager.

Each agent process gets one PTYSession. The session owns the PTY,
maintains a scrollback buffer, and manages a set of WebSocket subscribers.
The write_token capability controls who can send input.

Platform backends:
  Windows  → pty_windows.PtyWindows  (pywinpty / ConPTY)
  Mac/Linux → pty_unix.PtyUnix       (stdlib pty)
"""
from __future__ import annotations

import asyncio
import base64
import os
import secrets
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Platform backend selection
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    from pty_windows import PtyWindows as _PtyBackend
else:
    from pty_unix import PtyUnix as _PtyBackend  # type: ignore[import]


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

_SCROLLBACK_BYTES = 512 * 1024  # 512 KB cap on raw VT bytes


@dataclass
class PTYSession:
    """
    Owns a single PTY process and streams its output to subscribers.

    Attributes
    ----------
    session_id  : Stable UUID — survives subscriber churn and reconnects.
    agent_name  : Logical agent name ("claude", "codex", etc.).
    node        : Owning node name (this machine).
    cols, rows  : Current terminal dimensions.
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    agent_name: str = "claude"
    node: str = field(default_factory=lambda: os.environ.get("HOSTNAME", "local"))
    cols: int = 220
    rows: int = 50

    # Private state
    _pty: Any = field(default=None, init=False, repr=False)
    _write_token: str = field(default="", init=False, repr=False)
    _subscribers: set = field(default_factory=set, init=False, repr=False)
    _scrollback: bytearray = field(default_factory=bytearray, init=False, repr=False)
    _started_at: float = field(default=0.0, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    # Registered close callback (called when the process exits)
    _on_close: Callable[[str, str], None] | None = field(
        default=None, init=False, repr=False
    )

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def start(self, cmd: list[str]) -> None:
        """Spawn the agent process inside a PTY."""
        self._pty = _PtyBackend(cols=self.cols, rows=self.rows)
        self._pty.on_output(self._handle_output)
        self._write_token = secrets.token_urlsafe(32)
        self._started_at = time.time()
        await self._pty.start(cmd)
        asyncio.create_task(self._watch_exit())

    async def stop(self) -> None:
        """Terminate the PTY process and notify subscribers."""
        if self._closed:
            return
        self._closed = True
        if self._pty:
            await self._pty.stop()
        await self._broadcast({"type": "closed", "session_id": self.session_id,
                               "reason": "owner_closed"})

    # ------------------------------------------------------------------ #
    # Write / resize                                                       #
    # ------------------------------------------------------------------ #

    async def write(self, data: str, token: str) -> None:
        """Send keystrokes to the PTY. Raises PermissionError if token invalid."""
        if token != self._write_token:
            raise PermissionError("invalid write_token")
        if self._pty and not self._closed:
            await self._pty.write(data)

    async def resize(self, cols: int, rows: int, token: str) -> None:
        """Resize the PTY and broadcast resize_sync. Raises PermissionError if invalid."""
        if token != self._write_token:
            raise PermissionError("invalid write_token")
        self.cols = cols
        self.rows = rows
        if self._pty and not self._closed:
            await self._pty.resize(cols, rows)
        await self._broadcast({"type": "resize_sync", "session_id": self.session_id,
                               "cols": cols, "rows": rows})

    # ------------------------------------------------------------------ #
    # Capability                                                           #
    # ------------------------------------------------------------------ #

    def grant_write(self) -> str:
        """Return the write token. Call only from the session owner."""
        return self._write_token

    # ------------------------------------------------------------------ #
    # Subscribers                                                          #
    # ------------------------------------------------------------------ #

    async def subscribe(self, ws: Any, owner: bool = False) -> None:
        """
        Attach a WebSocket as a subscriber.

        Immediately sends the scrollback snapshot as an open_ack, then
        streams live output. Pass owner=True to include the write_token.
        """
        self._subscribers.add(ws)
        ack = {
            "type": "open_ack",
            "session_id": self.session_id,
            "write_token": self._write_token if owner else None,
            "scrollback": base64.b64encode(bytes(self._scrollback)).decode(),
        }
        await self._send_ws(ws, ack)

    async def unsubscribe(self, ws: Any) -> None:
        """Detach a WebSocket subscriber."""
        self._subscribers.discard(ws)

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def alive(self) -> bool:
        return bool(self._pty and self._pty.alive and not self._closed)

    @property
    def uptime(self) -> float:
        return time.time() - self._started_at if self._started_at else 0.0

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _handle_output(self, data: bytes) -> None:
        """Called by the PTY backend with raw VT bytes."""
        # Append to scrollback, trim if over cap
        self._scrollback.extend(data)
        if len(self._scrollback) > _SCROLLBACK_BYTES:
            trim = len(self._scrollback) - _SCROLLBACK_BYTES
            del self._scrollback[:trim]

        # Broadcast to all subscribers (fire-and-forget from sync context)
        msg = {
            "type": "data",
            "session_id": self.session_id,
            "data": base64.b64encode(data).decode(),
        }
        asyncio.ensure_future(self._broadcast(msg))

    async def _broadcast(self, msg: dict) -> None:
        """Send a message to all current subscribers, dropping dead ones."""
        dead: set = set()
        for ws in list(self._subscribers):
            try:
                await self._send_ws(ws, msg)
            except Exception:
                dead.add(ws)
        self._subscribers -= dead

    @staticmethod
    async def _send_ws(ws: Any, msg: dict) -> None:
        """Send JSON to a WebSocket (aiohttp or compatible interface)."""
        import json
        await ws.send_str(json.dumps(msg))

    async def _watch_exit(self) -> None:
        """Poll for process exit, broadcast closed, and remove from registry."""
        while self.alive:
            await asyncio.sleep(1)
        if not self._closed:
            self._closed = True
            await self._broadcast({"type": "closed", "session_id": self.session_id,
                                   "reason": "process_exited"})
            pty_registry.remove(self.session_id)


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

class PTYRegistry:
    """Global map of session_id → PTYSession."""

    def __init__(self) -> None:
        self._sessions: dict[str, PTYSession] = {}

    def get(self, session_id: str) -> PTYSession | None:
        return self._sessions.get(session_id)

    def register(self, session: PTYSession) -> None:
        self._sessions[session.session_id] = session

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list(self) -> list[dict]:
        return [
            {
                "session_id": s.session_id,
                "agent": s.agent_name,
                "node": s.node,
                "cols": s.cols,
                "rows": s.rows,
                "alive": s.alive,
                "uptime": round(s.uptime, 1),
                "subscribers": len(s._subscribers),
            }
            for s in self._sessions.values()
        ]


# Singleton used by agentrelay.py
pty_registry = PTYRegistry()
