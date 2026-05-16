"""
Windows ConPTY backend for AgentRelay terminal sessions.

Uses pywinpty (the Jupyter-maintained ConPTY binding) to create a
pseudoconsole, spawn an agent process inside it, and stream raw VT
bytes to/from subscribers.

Requires: pywinpty >= 2.0
"""
from __future__ import annotations

import asyncio
import sys
from typing import Callable

if sys.platform != "win32":
    raise ImportError("pty_windows is Windows-only")

import winpty  # pywinpty

from pty_env import terminal_env


class PtyWindows:
    """
    Thin async wrapper around a winpty.PtyProcess.

    Lifecycle:
        pty = PtyWindows(cols=220, rows=50)
        await pty.start(["claude", "--dangerously-skip-permissions"])
        pty.on_output(callback)   # called with raw VT bytes
        await pty.write("hello\n")
        await pty.resize(200, 40)
        await pty.stop()
    """

    def __init__(self, cols: int = 220, rows: int = 50) -> None:
        self.cols = cols
        self.rows = rows
        self._pty: winpty.PtyProcess | None = None
        self._reader_task: asyncio.Task | None = None
        self._output_cb: Callable[[bytes], None] | None = None
        self._running = False

    def on_output(self, callback: Callable[[bytes], None]) -> None:
        """Register a callback that receives raw VT bytes as they arrive."""
        self._output_cb = callback

    async def start(self, cmd: list[str]) -> None:
        """Spawn the process inside a ConPTY of the configured size."""
        self._pty = winpty.PtyProcess.spawn(
            cmd,
            dimensions=(self.rows, self.cols),
            env=terminal_env(self.cols, self.rows),
        )
        self._running = True
        self._reader_task = asyncio.create_task(self._read_loop())

    async def write(self, data: str) -> None:
        """Send keystrokes/text to the PTY process."""
        if self._pty and self._running:
            await asyncio.get_event_loop().run_in_executor(
                None, self._pty.write, data
            )

    async def resize(self, cols: int, rows: int) -> None:
        """Resize the ConPTY window."""
        self.cols = cols
        self.rows = rows
        if self._pty and self._running:
            await asyncio.get_event_loop().run_in_executor(
                None, self._pty.setwinsize, rows, cols
            )

    async def stop(self) -> None:
        """Terminate the PTY process and clean up."""
        self._running = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._pty:
            try:
                self._pty.close()
            except Exception:
                pass
            self._pty = None

    @property
    def alive(self) -> bool:
        """True if the child process is still running."""
        if not self._pty:
            return False
        return self._pty.isalive()

    async def _read_loop(self) -> None:
        """Background task: read PTY output and fire the output callback."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                data = await loop.run_in_executor(None, self._read_chunk)
                if data and self._output_cb:
                    self._output_cb(data)
                elif not self._pty or not self._pty.isalive():
                    self._running = False
                    break
            except Exception:
                self._running = False
                break

    def _read_chunk(self) -> bytes:
        """Blocking read of one chunk from the PTY (run in executor)."""
        if not self._pty:
            return b""
        try:
            text = self._pty.read(4096)
            return text.encode("utf-8", errors="replace") if isinstance(text, str) else text
        except EOFError:
            return b""
