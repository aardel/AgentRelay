"""
Mac/Linux PTY backend for AgentRelay terminal sessions.

Uses the stdlib pty module to open a pseudoterminal, spawn the agent
process inside it, and stream raw VT bytes to the caller via a callback.

No external dependencies — pty is always available on Mac/Linux.
"""
from __future__ import annotations

import asyncio
import fcntl
import os
import struct
import sys
import termios
from typing import Callable

if sys.platform == "win32":
    raise ImportError("pty_unix is Mac/Linux only")

import pty  # stdlib

from pty_env import build_pty_env


class PtyUnix:
    """
    Thin async wrapper around a stdlib pty pair.

    Lifecycle:
        p = PtyUnix(cols=220, rows=50)
        p.on_output(callback)
        await p.start(["claude", "--dangerously-skip-permissions"])
        await p.write("hello\\n")
        await p.resize(200, 40)
        await p.stop()
    """

    def __init__(self, cols: int = 220, rows: int = 50) -> None:
        self.cols = cols
        self.rows = rows
        self._master_fd: int | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._output_cb: Callable[[bytes], None] | None = None
        self._running = False

    def on_output(self, callback: Callable[[bytes], None]) -> None:
        """Register a callback that receives raw VT bytes as they arrive."""
        self._output_cb = callback

    async def start(self, cmd: list[str]) -> None:
        """Spawn the process inside a pty of the configured size."""
        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd
        self._set_winsize(master_fd, self.cols, self.rows)

        env = build_pty_env(self.cols, self.rows)
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True, env=env,
        )
        os.close(slave_fd)
        self._running = True
        self._reader_task = asyncio.get_running_loop().create_task(self._read_loop())

    async def write(self, data: str) -> None:
        """Send keystrokes/text to the PTY process."""
        if self._master_fd is not None and self._running:
            raw = data.encode("utf-8") if isinstance(data, str) else data
            await asyncio.get_running_loop().run_in_executor(None, os.write, self._master_fd, raw)

    async def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window."""
        self.cols = cols
        self.rows = rows
        if self._master_fd is not None and self._running:
            self._set_winsize(self._master_fd, cols, rows)

    async def stop(self) -> None:
        """Terminate the PTY process and clean up."""
        self._running = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        if self._master_fd is not None:
            loop = asyncio.get_running_loop()
            try:
                loop.remove_reader(self._master_fd)
            except Exception:
                pass
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

    @property
    def alive(self) -> bool:
        """True if the child process is still running."""
        return bool(self._proc and self._proc.returncode is None and self._running)

    def _set_winsize(self, fd: int, cols: int, rows: int) -> None:
        # TIOCSWINSZ struct: rows, cols, xpix, ypix (all unsigned short)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    async def _read_loop(self) -> None:
        """Stream PTY output via loop.add_reader — no polling thread needed."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def _readable() -> None:
            fd = self._master_fd
            if fd is None:
                queue.put_nowait(b"")
                return
            try:
                chunk = os.read(fd, 65536)
                queue.put_nowait(chunk)
            except OSError:
                # EIO: slave closed (process exited)
                try:
                    loop.remove_reader(fd)
                except Exception:
                    pass
                queue.put_nowait(b"")

        loop.add_reader(self._master_fd, _readable)
        try:
            while self._running:
                data = await queue.get()
                if not data:
                    break
                if self._output_cb:
                    self._output_cb(data)
        except asyncio.CancelledError:
            pass
        finally:
            if self._master_fd is not None:
                try:
                    loop.remove_reader(self._master_fd)
                except Exception:
                    pass
            self._running = False
