"""Tests for PTY spawn environment and argv resolution."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

from pty_env import build_pty_env, resolve_pty_argv


def test_build_pty_env_overrides_dumb_term(monkeypatch):
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("CI", "1")
    env = build_pty_env(120, 40)
    assert env["TERM"] == "xterm-256color"
    assert env["COLORTERM"] == "truecolor"
    assert env["FORCE_COLOR"] == "3"
    assert env["COLUMNS"] == "120"
    assert env["LINES"] == "40"
    assert "NO_COLOR" not in env
    assert "CI" not in env


def test_build_pty_env_preserves_other_vars(monkeypatch):
    monkeypatch.setenv("MY_VAR", "keep")
    env = build_pty_env(80, 24)
    assert env["MY_VAR"] == "keep"


def test_resolve_pty_argv_gemini_cmd(monkeypatch, tmp_path):
    if sys.platform != "win32":
        return
    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    script = npm_dir / "node_modules" / "pkg" / "bundle" / "gemini.js"
    script.parent.mkdir(parents=True)
    script.write_text("// gemini", encoding="utf-8")
    cmd = npm_dir / "gemini.cmd"
    cmd.write_text(
        'endLocal & "%_prog%" "%dp0%\\node_modules\\pkg\\bundle\\gemini.js" %*\n',
        encoding="utf-8",
    )
    node = npm_dir / "node.exe"
    node.write_bytes(b"")

    monkeypatch.setenv("PATH", str(npm_dir))
    with mock.patch("pty_env._short_path", side_effect=lambda p: p):
        argv = resolve_pty_argv(["gemini", "--help"])
    assert argv[0] == str(node)
    assert argv[1] == str(script.resolve())
    assert argv[2:] == ["--help"]
