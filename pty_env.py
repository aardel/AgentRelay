"""
Environment helpers for embedded AgentRelay terminal sessions.
"""
from __future__ import annotations

import os


def terminal_env(cols: int, rows: int) -> dict[str, str]:
    """
    Return a child-process environment for an xterm.js-backed PTY.

    TERM and COLORTERM advertise ANSI/256-color/true-color capability while
    keeping user-level opt-outs such as NO_COLOR intact.
    """
    env = os.environ.copy()
    # Child PTY sessions should use color; parent NO_COLOR must not force monochrome.
    env.pop("NO_COLOR", None)
    env.update({
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
        "CLICOLOR": "1",
        "FORCE_COLOR": "1",
        "COLUMNS": str(cols),
        "LINES": str(rows),
    })
    return env
