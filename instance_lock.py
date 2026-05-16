"""PID-file locks for single-instance daemon and GUI."""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from pathlib import Path


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        if pid == os.getpid():
            return True
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except Exception:
            return False
        return result.returncode == 0 and str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_pid_lock(pid_file: Path) -> bool:
    while True:
        try:
            fd = os.open(pid_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            try:
                existing_pid = int(pid_file.read_text().strip())
            except ValueError:
                pid_file.unlink(missing_ok=True)
                continue
            if pid_is_running(existing_pid):
                return False
            pid_file.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return True


def release_pid_lock(pid_file: Path) -> None:
    try:
        if pid_file.exists() and int(pid_file.read_text().strip()) == os.getpid():
            pid_file.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


def gui_pid_file() -> Path:
    return Path(tempfile.gettempdir()) / "agentrelay-gui.pid"


def daemon_pid_file() -> Path:
    return Path(tempfile.gettempdir()) / "agentrelay.pid"
