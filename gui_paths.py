"""Resolve bundled GUI assets for dev installs and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def gui_directory() -> Path:
    """Directory containing index.html and static UI assets."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        candidates.append(meipass / "gui")
    candidates.append(Path(__file__).resolve().parent / "gui")
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return candidates[-1]
