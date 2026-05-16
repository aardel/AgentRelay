#!/usr/bin/env python3
"""Print the local AgentRelay UI URL for a config file (used by Launch-AgentRelay.cmd)."""

from __future__ import annotations

import sys

import yaml


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: print_ui_url.py <config.yaml>", file=sys.stderr)
        sys.exit(2)
    cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
    port = cfg["port"]
    token = cfg["token"]
    print(f"http://127.0.0.1:{port}/?token={token}&port={port}")


if __name__ == "__main__":
    main()
