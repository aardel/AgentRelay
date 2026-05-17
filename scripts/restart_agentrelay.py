#!/usr/bin/env python3
"""Relaunch AgentRelay after /api/app/restart (daemon schedules this detached)."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from instance_lock import daemon_pid_file, gui_pid_file, pid_is_running


def _kill_pid_file(pid_file: Path) -> None:
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return
    if pid_is_running(pid):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    pid_file.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()
    time.sleep(max(0.5, args.delay))
    _kill_pid_file(daemon_pid_file())
    _kill_pid_file(gui_pid_file())
    gui = ROOT / "agentrelay_gui.py"
    config = args.config.resolve()
    py = sys.executable
    if os.name == "nt" and py.lower().endswith("python.exe"):
        pyw = Path(py).with_name("pythonw.exe")
        if pyw.exists():
            py = str(pyw)
    kwargs: dict = {"cwd": str(ROOT)}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([py, str(gui), "--config", str(config)], **kwargs)


if __name__ == "__main__":
    main()
