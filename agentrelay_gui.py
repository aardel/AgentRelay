#!/usr/bin/env python3
"""Starts the AgentRelay desktop app (embedded web UI by default)."""

from __future__ import annotations

import sys


def main() -> None:
    if "--tk" in sys.argv or "--legacy-tk" in sys.argv:
        argv = [a for a in sys.argv if a not in ("--tk", "--legacy-tk")]
        sys.argv = argv
        from agentrelay_app import main as tk_main

        tk_main()
        return
    from agentrelay_web import main as web_main

    web_main()


if __name__ == "__main__":
    main()
