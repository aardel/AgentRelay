"""Shared environment and argv resolution for PTY-spawned agent processes."""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

_NPM_CMD_SCRIPT = re.compile(r'"%~?dp0%\\([^"]+)"', re.IGNORECASE)


def build_pty_env(cols: int, rows: int) -> dict[str, str]:
    """
    Terminal env for embedded / ConPTY sessions.

    Agent CLIs (Gemini, Claude, Codex) probe TERM, COLORTERM, and color depth.
    Headless daemons often inherit TERM=dumb or CI=1, which disables rich output.
    """
    env = os.environ.copy()
    for key in ("NO_COLOR", "CLICOLOR", "NODE_DISABLE_COLORS"):
        env.pop(key, None)
    if env.get("CI"):
        env.pop("CI", None)
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["FORCE_COLOR"] = "3"
    env["CLICOLOR_FORCE"] = "1"
    env["COLUMNS"] = str(cols)
    env["LINES"] = str(rows)
    env["TERM_PROGRAM"] = "AgentRelay"
    return env


def resolve_pty_argv(argv: list[str]) -> list[str]:
    """
    Normalize launch argv for PTY backends.

    On Windows, npm global shims are .cmd files that re-launch via cmd.exe;
    spawn node + script directly so ConPTY, TERM, and color detection work.
    """
    if sys.platform != "win32" or not argv:
        return argv
    exe = argv[0]
    resolved = shutil.which(exe)
    if not resolved or not resolved.lower().endswith(".cmd"):
        out = list(argv)
        out[0] = _short_path(resolved or exe)
        return out
    cmd_path = Path(resolved)
    npm_argv = _npm_cmd_to_argv(cmd_path, argv[1:])
    if npm_argv:
        return npm_argv
    return [_short_path(resolved), *argv[1:]]


def _npm_cmd_to_argv(cmd_path: Path, args: list[str]) -> list[str] | None:
    text = cmd_path.read_text(encoding="utf-8", errors="replace")
    match = _NPM_CMD_SCRIPT.search(text)
    if not match:
        return None
    rel = match.group(1)
    if not rel.lower().endswith((".js", ".mjs", ".cjs")):
        return None
    script = (cmd_path.parent / rel).resolve()
    if not script.is_file():
        return None
    bundled_node = cmd_path.parent / "node.exe"
    node = bundled_node if bundled_node.is_file() else shutil.which("node")
    if not node:
        return None
    return [_short_path(str(node)), _short_path(str(script)), *args]


def _short_path(path: str) -> str:
    """8.3 path so pywinpty can spawn executables under 'Program Files'."""
    if sys.platform != "win32" or " " not in path:
        return path
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf)):
            return buf.value or path
    except Exception:
        pass
    return path
