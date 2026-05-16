#!/usr/bin/env python3
"""
AgentRelay desktop shell — starts the local relay daemon and opens the web UI.

Cross-platform: uses pywebview (WebView2 on Windows, WebKit on macOS, GTK/Qt on Linux).
Pass --browser to open the system browser instead (development).
Pass --tk for the legacy Tkinter UI.
"""

from __future__ import annotations

import argparse
import atexit
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

from agentrelay import DEFAULT_CONFIG, Config
from instance_lock import acquire_pid_lock, gui_pid_file, release_pid_lock
from relay_client import relay_running, start_relay


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(__file__).resolve().parent


ROOT = _project_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ui_url(port: int, token: str) -> str:
    return f"http://127.0.0.1:{port}/?token={quote(token)}&port={port}"


def main() -> None:
    p = argparse.ArgumentParser(prog="agentrelay-gui")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument(
        "--browser",
        action="store_true",
        help="open in the system browser instead of an embedded window",
    )
    args = p.parse_args()
    config_path = args.config

    if not config_path.exists():
        print(
            "No settings found.\n"
            "Run: agentrelay --init\n"
            "Or copy config.example.yaml to config.yaml",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = Config.load(config_path)
    if not relay_running(cfg) and not start_relay(config_path):
        print("Could not start AgentRelay daemon.", file=sys.stderr)
        sys.exit(1)

    url = _ui_url(cfg.port, cfg.token)
    gui_lock = gui_pid_file()
    if not acquire_pid_lock(gui_lock):
        webbrowser.open(url)
        print("AgentRelay is already running — opened the existing UI.")
        sys.exit(0)
    atexit.register(release_pid_lock, gui_lock)

    if args.browser:
        webbrowser.open(url)
        print(f"AgentRelay UI: {url}")
        print("Press Ctrl+C to exit (daemon keeps running).")
        try:
            while True:
                import time
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return

    try:
        import webview
    except ImportError:
        print(
            "pywebview is required for the desktop UI.\n"
            "  pip install pywebview\n"
            "On Linux you may also need: pip install pywebview[gtk]\n"
            "Or use: agentrelay-gui --browser",
            file=sys.stderr,
        )
        sys.exit(1)

    window = webview.create_window(
        "AgentRelay",
        url,
        width=1180,
        height=760,
        min_size=(800, 560),
        text_select=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
