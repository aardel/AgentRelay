#!/usr/bin/env python3
"""
agentrelay - peer-to-peer AI agent command relay.

Each machine runs this daemon. It:
  - Advertises itself via mDNS as _agentrelay._tcp.local.
  - Discovers peer machines automatically on the LAN.
  - Accepts commands via HTTP (token-authenticated).
  - Routes each command via a policy engine:
        auto     - whitelist auto-execute without a shell
        agent    - hand to a local AI agent CLI (claude/codex/gemini)
        approve  - native OS dialog blocks until user approves
        reject   - refuse

Usage:
    agentrelay --init        # write a default config and a fresh token
    agentrelay               # run the daemon (reads ~/.config/agentrelay/config.yaml)
    agentrelay --verbose     # debug logging
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import dataclasses
import json
import logging
import os
import platform
import atexit
import re
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hashlib

import aiohttp
import yaml
from aiohttp import web
from zeroconf import IPVersion, ServiceInfo, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from gui_paths import gui_directory
from pairing import PairingManager
from talk import ConversationStore
from pty_session import PTYSession, pty_registry
from task_queue import TaskQueue
from ssh_hosts import (
    SSHHost,
    build_ssh_shell_argv,
    describe_ssh_argv,
    get_machine_id,
    get_store as get_ssh_store,
    test_ssh_connectivity,
)
from agent_data import AgentDataStore
from idea_store import IdeaStore
from bug_store import BugStore

SERVICE_TYPE = "_agentrelay._tcp.local."
INTERACTIVE_MODES = frozenset({"interactive", "interactive_tmux"})
DISCOVERY_BROADCAST = "255.255.255.255"


def _token_hash(token: str) -> str:
    """Short hash used in peer payloads to verify shared secret without exposing it."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP listener for LAN broadcast peer discovery."""

    def __init__(self, relay: "AgentRelay") -> None:
        self.relay = relay
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = json.loads(data.decode())
        except Exception:
            return
        node = msg.get("node", "")
        if not node or node == self.relay.cfg.node_name:
            return
        token_hash = msg.get("token_hash", "")
        if not token_hash or not secrets.compare_digest(
            token_hash, _token_hash(self.relay.cfg.token)
        ):
            return
        address = addr[0]  # use actual source IP, not the payload field
        port = int(msg.get("port") or self.relay.cfg.port)
        agents = msg.get("agents", "")
        active_agents = msg.get("active_agents", "")
        self.relay.peers.upsert(node, address, port,
                                agents=agents, active_agents=active_agents)
        asyncio.ensure_future(self.relay._announce_to_peer(address, port))

    def error_received(self, exc: Exception) -> None:
        log.debug("UDP discovery error: %s", exc)
INTERACTIVE_SUFFIXES = ("-interactive", "-visible")


def agent_base_name(agent_name: str) -> str:
    for suffix in INTERACTIVE_SUFFIXES:
        if agent_name.endswith(suffix):
            return agent_name[: -len(suffix)]
    return agent_name
DEFAULT_PORT = 9876
DEFAULT_CONFIG = Path.home() / ".config" / "agentrelay" / "config.yaml"
AUTO_ALLOWLIST = {"uname", "hostname", "whoami", "pwd", "ls", "df", "free",
                  "uptime", "date", "id"}

log = logging.getLogger("agentrelay")

# Persistent task queue (SQLite-backed).  Lazy-init on first use so unit tests
# can import this module without touching the filesystem.
_task_queue: TaskQueue | None = None

# SSE subscriber queues — one per connected browser tab watching /api/tasks/events.
_task_event_queues: list[asyncio.Queue] = []


def _notify_task_event(task_id: str, status: str) -> None:
    """Push a task-changed notification to all SSE subscribers (fire-and-forget)."""
    payload = {"task_id": task_id, "status": status}
    for q in list(_task_event_queues):
        q.put_nowait(payload)


def get_task_queue() -> TaskQueue:
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue


async def _push_status_callback(
    reply_to: str,
    originator_task_id: str,
    status: str,
    *,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """POST a status update back to the originating machine."""
    payload: dict = {"task_id": originator_task_id, "status": status}
    if result is not None:
        payload["result"] = result
    if error:
        payload["error"] = error
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await session.post(reply_to, json=payload)
    except Exception as exc:
        log.warning("status callback to %s failed: %s", reply_to, exc)


# Deliveries queued for the GUI app to type into the agent window.
# Used on Windows where the GUI process has foreground activation permission
# and can focus windows reliably (unlike the daemon, which can't when
# Chrome Remote Desktop or another remote session holds focus).
_gui_delivery_queue: list[dict] = []

# Peers seen via /peer-announce that have no saved SSH preset yet.
# GUI polls /api/ssh-hosts/pending-presets and clears on read.
_pending_ssh_presets: list[dict] = []

# Inbox: all incoming dispatches stored here so skills can poll for replies.
# Capped at 200 entries; oldest are dropped when full.
_dispatch_inbox: list[dict] = []
_INBOX_MAX = 200

GLOBAL_BROADCAST_PREFIX = (
    "═══ AgentRelay GLOBAL BROADCAST ═══\n"
    "This message is sent to ALL agents simultaneously.\n"
    "Treat it as a shared instruction for every agent.\n"
    "══════════════════════════════════\n\n"
)


def pid_file_path() -> Path:
    return Path(tempfile.gettempdir()) / "agentrelay.pid"


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


# ============================================================
# Configuration
# ============================================================

@dataclass
class AdapterConfig:
    """How to invoke a local AI agent CLI in headless / one-shot mode."""
    name: str
    command: list[str]   # e.g. ["claude", "-p", "{prompt}"]
    timeout: int = 1800  # seconds
    mode: str = "headless"          # "headless" | "interactive" | "interactive_tmux"
    session: str | None = None      # tmux session name for interactive mode
    label: str | None = None        # friendly name shown in the app
    window_title: str | None = None # window title fragment to focus before typing
    role: str | None = None         # e.g. "reasoning" | "execution" | "review"
    capabilities: list[str] = None  # e.g. ["planning", "synthesis"] or ["code_edit", "tests"]

    def __post_init__(self) -> None:
        if self.capabilities is None:
            self.capabilities = []


@dataclass
class PolicyRule:
    """A single pattern-matched routing rule."""
    pattern: str
    action: str          # "auto" | "agent" | "approve" | "reject"
    agent: str | None = None   # which adapter for action="agent"


@dataclass
class Config:
    node_name: str
    port: int
    token: str
    adapters: dict[str, AdapterConfig]
    rules: list[PolicyRule]
    default_action: str          # one of: auto | agent | approve | reject
    default_agent: str | None
    approve_timeout: int         # seconds for dialog to wait
    use_tmux: bool
    wait_before_send_seconds: int
    trusted_peers: list[str]
    agentmemory: Any = None  # AgentmemoryConfig; optional sidecar bridge

    @classmethod
    def load(cls, path: Path) -> "Config":
        return cls.load_dict(yaml.safe_load(path.read_text()))

    @classmethod
    def load_dict(cls, data: dict[str, Any]) -> "Config":
        from agentmemory_bridge import AgentmemoryConfig

        adapters = {
            name: AdapterConfig(name=name, **spec)
            for name, spec in (data.get("adapters") or {}).items()
        }
        rules = [PolicyRule(**r) for r in data.get("rules") or []]
        relay = data.get("relay") or {}
        for spec in adapters.values():
            if spec.mode == "interactive_tmux":
                spec.mode = "interactive"
            if not spec.label:
                spec.label = spec.name.replace("-", " ").title()
        return cls(
            node_name=data.get("node_name") or socket.gethostname().split(".")[0],
            port=int(data.get("port") or DEFAULT_PORT),
            token=data["token"],
            adapters=adapters,
            rules=rules,
            default_action=data.get("default_action", "approve"),
            default_agent=data.get("default_agent"),
            approve_timeout=int(data.get("approve_timeout") or 300),
            use_tmux=bool(data.get("use_tmux", False)),
            wait_before_send_seconds=int(
                relay.get("wait_before_send_seconds") or 5),
            trusted_peers=list(data.get("trusted_peers") or []),
            agentmemory=AgentmemoryConfig.from_dict(data.get("agentmemory")),
        )

    def agent_labels(self) -> list[dict[str, str]]:
        out = []
        for name, spec in self.adapters.items():
            mode = "visible" if spec.mode in INTERACTIVE_MODES else "background"
            entry: dict = {"id": name, "label": spec.label or name, "mode": mode}
            if spec.role:
                entry["role"] = spec.role
            if spec.capabilities:
                entry["capabilities"] = spec.capabilities
            out.append(entry)
        return out

    def resolve_adapter_name(
        self,
        requested: str | None,
        *,
        prefer_interactive: bool = False,
        active_agents: list[str] | None = None,
    ) -> str | None:
        """Resolve base agent names to configured adapter IDs.

        `prefer_interactive=True` is used by visible delivery paths, allowing
        a request for "gemini" to land in "gemini-interactive" when available.
        Background paths keep exact adapter behavior first.

        When *active_agents* is non-empty, only adapters in that family are
        returned so forwards do not spawn or retarget to a different agent.
        """
        if not requested:
            return None

        active = list(active_agents or [])
        if active and not _agent_family_matches(requested, active):
            return None

        if prefer_interactive:
            exact = self.adapters.get(requested)
            if exact and exact.mode in INTERACTIVE_MODES:
                if not active or _agent_family_matches(requested, active):
                    return requested
            base = agent_base_name(requested)
            for candidate in (f"{base}-interactive", f"{base}-visible"):
                spec = self.adapters.get(candidate)
                if spec and spec.mode in INTERACTIVE_MODES:
                    if not active or _agent_family_matches(candidate, active):
                        return candidate

        if requested in self.adapters:
            if not active or _agent_family_matches(requested, active):
                return requested

        base = agent_base_name(requested)
        if base in self.adapters:
            if not active or _agent_family_matches(base, active):
                return base
        for candidate in (f"{base}-interactive", f"{base}-visible"):
            if candidate in self.adapters:
                if not active or _agent_family_matches(candidate, active):
                    return candidate
        return None


# ============================================================
# Policy engine
# ============================================================

def decide(cfg: Config, command: str,
           hint: str | None) -> tuple[str, str | None]:
    """Return (action, agent_name) for the given command."""
    first_match: PolicyRule | None = None
    guard_match: PolicyRule | None = None
    for rule in cfg.rules:
        if re.search(rule.pattern, command):
            if first_match is None:
                first_match = rule
            if rule.action in ("approve", "reject"):
                guard_match = rule
                break

    # Caller hints may raise scrutiny, but cannot downgrade a policy rule that
    # requires approval or rejection, even if an older config puts broad rules
    # before dangerous-command rules.
    if guard_match:
        if hint == "reject":
            return "reject", None
        return guard_match.action, guard_match.agent or cfg.default_agent

    if hint in ("approve", "reject"):
        return hint, None
    if hint == "agent":
        return hint, cfg.default_agent
    if hint == "auto":
        if first_match and first_match.action != "auto":
            return first_match.action, first_match.agent or cfg.default_agent
        return hint, None

    if first_match:
        return first_match.action, first_match.agent or cfg.default_agent
    return cfg.default_action, cfg.default_agent


# ============================================================
# Notifications & approvals (cross-platform, best-effort)
# ============================================================

def notify(title: str, body: str) -> None:
    """Best-effort native notification (macOS / Linux / Windows)."""
    sysname = platform.system()
    body_clean = body.replace('"', "'")
    title_clean = title.replace('"', "'")
    try:
        if sysname == "Darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{body_clean}" with title "{title_clean}"'],
                check=False, timeout=5,
            )
        elif sysname == "Linux":
            if shutil.which("notify-send"):
                subprocess.run(["notify-send", title, body],
                               check=False, timeout=5)
        elif sysname == "Windows":
            ps = (
                "[Windows.UI.Notifications.ToastNotificationManager,"
                "Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null;"
                f'Write-Host "{title_clean}: {body_clean}"'
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           check=False, timeout=5)
    except Exception as e:
        log.warning("notify failed: %s", e)


def approve_dialog(cfg: Config, sender: str, command: str) -> bool:
    """Blocking approve/reject dialog. Returns True if user approves."""
    sysname = platform.system()
    timeout = cfg.approve_timeout
    prompt = f"Run command from {sender}?\n\n{command}"
    safe_prompt = prompt.replace('"', "'")
    try:
        if sysname == "Darwin":
            script = (
                f'display dialog "{safe_prompt}" '
                f'buttons {{"Reject", "Approve"}} default button "Approve" '
                f'with title "agentrelay" giving up after {timeout}'
            )
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True,
                               timeout=timeout + 5)
            return "Approve" in (r.stdout or "")
        elif sysname == "Linux":
            if shutil.which("zenity"):
                r = subprocess.run(
                    ["zenity", "--question",
                     f"--title=agentrelay from {sender}",
                     f"--text={prompt}",
                     f"--timeout={timeout}"],
                    check=False, timeout=timeout + 5,
                )
                return r.returncode == 0
            if shutil.which("kdialog"):
                r = subprocess.run(
                    ["kdialog", "--title", f"agentrelay from {sender}",
                     "--yesno", prompt],
                    check=False, timeout=timeout + 5,
                )
                return r.returncode == 0
            log.warning("no zenity/kdialog available; auto-rejecting")
            return False
        elif sysname == "Windows":
            ps = (
                "Add-Type -AssemblyName PresentationFramework;"
                f'$r=[System.Windows.MessageBox]::Show("{safe_prompt}",'
                '"agentrelay",4);'
                'if ($r -eq "Yes") {exit 0} else {exit 1}'
            )
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               check=False, timeout=timeout + 5)
            return r.returncode == 0
    except Exception as e:
        log.warning("approve dialog failed: %s", e)
    return False


# ============================================================
# Execution
# ============================================================

async def run_subprocess(cmd: list[str] | str, timeout: int,
                         shell: bool = False) -> dict[str, Any]:
    """Run a subprocess and capture stdout/stderr."""
    log.info("exec: %s", cmd)
    if shell:
        proc = await asyncio.create_subprocess_shell(
            cmd if isinstance(cmd, str) else " ".join(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return {"status": "timeout", "exit_code": -1,
                "stdout": "", "stderr": f"timeout after {timeout}s"}
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "exit_code": proc.returncode,
        "stdout": (out or b"").decode(errors="replace"),
        "stderr": (err or b"").decode(errors="replace"),
    }


def render_adapter(adapter: AdapterConfig, prompt: str) -> list[str]:
    return [part.replace("{prompt}", prompt) for part in adapter.command]


async def spawn_agent(cfg: Config, adapter: AdapterConfig,
                      prompt: str) -> dict[str, Any]:
    if adapter.mode in INTERACTIVE_MODES:
        return await _spawn_interactive_visible(
            adapter, prompt, cfg.wait_before_send_seconds)
    cmd = render_adapter(adapter, prompt)
    if cfg.use_tmux and shutil.which("tmux"):
        session = f"agentrelay-{uuid.uuid4().hex[:6]}"
        tmux_cmd = ["tmux", "new-session", "-d", "-s", session,
                    " ".join(shlex.quote(c) for c in cmd)]
        await run_subprocess(tmux_cmd, timeout=10)
        return {"status": "spawned",
                "exit_code": 0,
                "stdout": (
                    f"spawned in tmux session '{session}'.\n"
                    f"attach with: tmux attach -t {session}"),
                "stderr": ""}
    return await run_subprocess(cmd, timeout=adapter.timeout)


async def _on_session_closed(
    tq: TaskQueue,
    local_task_id: str,
    originator_task_id: str,
    reply_to: str,
    reason: str,
) -> None:
    """Mark the local task complete/failed and push status back to originator."""
    status = "failed" if reason == "owner_closed" else "completed"
    await tq.update_status(local_task_id, status)
    _notify_task_event(local_task_id, status)
    await _push_status_callback(reply_to, originator_task_id, status)


def list_active_agent_names() -> list[str]:
    """Agent adapter IDs that currently have a live embedded terminal."""
    return pty_registry.list_active_agent_names()


def _agent_family_matches(name: str, active: list[str]) -> bool:
    if not active:
        return True
    if name in active:
        return True
    base = agent_base_name(name)
    return any(agent_base_name(a) == base for a in active)


def _find_pty_for_adapter(adapter_name: str) -> PTYSession | None:
    """Return an embedded GUI terminal session for this adapter, if running."""
    session = pty_registry.find_alive_by_agent(adapter_name)
    if session:
        return session
    base = adapter_name.split("-", 1)[0]
    if base != adapter_name:
        return pty_registry.find_alive_by_agent(base)
    return None


async def _deliver_prompt_to_pty(adapter_name: str, prompt: str,
                                 wait_seconds: int) -> bool:
    """Type a prompt into an embedded /terminal PTY session (web GUI)."""
    session = _find_pty_for_adapter(adapter_name)
    if not session:
        return False
    token = session.grant_write()
    try:
        await session.write(prompt, token)
        await asyncio.sleep(max(1, wait_seconds))
        await session.write("\r", token)
    except Exception as exc:
        log.warning("pty delivery failed for %s: %s", adapter_name, exc)
        return False
    return True


async def _spawn_interactive_visible(adapter: AdapterConfig, prompt: str,
                                     wait_seconds: int) -> dict[str, Any]:
    """Type the prompt into the active agent window, wait, then press Enter."""
    if await _deliver_prompt_to_pty(adapter.name, prompt, wait_seconds):
        return {
            "status": "sent", "exit_code": 0,
            "stdout": (
                f"Delivered to embedded terminal for '{adapter.name}', "
                f"sent after {wait_seconds}s."),
            "stderr": "",
        }

    active = list_active_agent_names()
    if active and not _agent_family_matches(adapter.name, active):
        active_text = ", ".join(active)
        return {
            "status": "error",
            "exit_code": 1,
            "stdout": "",
            "stderr": (
                f"Agent '{adapter.name}' is not running on this computer. "
                f"Open that agent's terminal first, or send to: {active_text}"
            ),
            "active_agents": active,
        }

    # Derive a window title fragment: explicit config > first word of command
    title_hint = (adapter.window_title or
                  (adapter.command[0] if adapter.command else "")).lower()

    if platform.system() == "Windows":
        # On Windows the GUI app (agentrelay_app.py) owns window focus+typing.
        # It runs in the user's session with foreground activation permission,
        # so it can set focus even when Chrome Remote Desktop is active.
        _gui_delivery_queue.append({
            "id": uuid.uuid4().hex,
            "adapter_name": adapter.name,
            "prompt": prompt,
            "title_hint": title_hint,
            "wait_seconds": wait_seconds,
        })
        return {
            "status": "queued", "exit_code": 0,
            "stdout": "Queued for GUI delivery.",
            "stderr": "",
        }

    if shutil.which("tmux"):
        session = adapter.session or f"agentrelay-{adapter.name}"
        check = await run_subprocess(
            ["tmux", "has-session", "-t", session], timeout=5)
        if check["exit_code"] != 0 and adapter.command:
            await run_subprocess(
                ["tmux", "new-session", "-d", "-s", session] + list(adapter.command),
                timeout=10,
            )
            await asyncio.sleep(2)
            check = await run_subprocess(
                ["tmux", "has-session", "-t", session], timeout=5)
        if check["exit_code"] == 0:
            send = await run_subprocess(
                ["tmux", "send-keys", "-t", session, prompt], timeout=10)
            if send["exit_code"] != 0:
                return {"status": "error", "exit_code": send["exit_code"],
                        "stdout": "", "stderr": send["stderr"]}
            await asyncio.sleep(max(1, wait_seconds))
            enter = await run_subprocess(
                ["tmux", "send-keys", "-t", session, "", "Enter"], timeout=10)
            if enter["exit_code"] != 0:
                return {"status": "error", "exit_code": enter["exit_code"],
                        "stdout": "", "stderr": enter["stderr"]}
            return {
                "status": "sent", "exit_code": 0,
                "stdout": (
                    f"Typed into tmux session '{session}', "
                    f"sent after {wait_seconds}s."),
                "stderr": "",
            }

    # No tmux — pyautogui fallback for Mac/Linux without tmux
    try:
        import pyautogui
        loop = asyncio.get_running_loop()

        def _focus_and_type():
            import time
            focused_on = "active window"
            if title_hint:
                if platform.system() == "Windows":
                    try:
                        import ctypes
                        import ctypes.wintypes
                        import pygetwindow as gw
                        matches = [w for w in gw.getAllWindows()
                                   if title_hint in w.title.lower()]
                        if matches:
                            matches[0].activate()
                            time.sleep(0.4)
                            focused_on = matches[0].title
                    except Exception:
                        pass
                elif platform.system() == "Darwin":
                    try:
                        script = (
                            f'tell application "System Events" to set frontmost of '
                            f'(first process whose name contains "{title_hint}") to true'
                        )
                        subprocess.run(["osascript", "-e", script],
                                       check=False, timeout=3)
                        time.sleep(0.4)
                        focused_on = title_hint
                    except Exception:
                        pass
            time.sleep(0.2)
            pyautogui.write(prompt, interval=0.02)
            return focused_on

        focused_on = await loop.run_in_executor(None, _focus_and_type)
        await asyncio.sleep(max(1, wait_seconds))
        await loop.run_in_executor(None, pyautogui.press, "enter")
        return {
            "status": "sent", "exit_code": 0,
            "stdout": f"Typed into '{focused_on}', Enter pressed after {wait_seconds}s.",
            "stderr": "",
        }
    except Exception as e:
        return {
            "status": "error", "exit_code": 1, "stdout": "",
            "stderr": f"pyautogui fallback failed: {e}",
        }


async def auto_execute(command: str) -> dict[str, Any]:
    """Execute a small allowlist without invoking a shell."""
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return {"status": "rejected", "exit_code": 1, "stdout": "",
                "stderr": f"invalid command syntax: {e}"}

    if not argv or argv[0] not in AUTO_ALLOWLIST:
        return {"status": "rejected", "exit_code": 1, "stdout": "",
                "stderr": f"auto command not allowed: {argv[0] if argv else ''}"}

    return await run_subprocess(argv, timeout=600)


# ============================================================
# Peer registry
# ============================================================

@dataclass
class Peer:
    name: str
    address: str
    port: int
    agents: str = ""
    active_agents: str = ""
    last_seen: float = field(default_factory=time.time)


class PeerRegistry:
    def __init__(self) -> None:
        self.peers: dict[str, Peer] = {}

    def upsert(self, name: str, addr: str, port: int,
               agents: str = "", active_agents: str = "") -> None:
        self.peers[name] = Peer(
            name=name, address=addr, port=port,
            agents=agents, active_agents=active_agents)
        log.info("peer up: %s @ %s:%d", name, addr, port)

    def remove(self, name: str) -> None:
        if name in self.peers:
            log.info("peer down: %s", name)
            del self.peers[name]

    def list(self, trusted: list[str] | None = None) -> list[dict[str, Any]]:
        # trusted parameter kept for backward compat but ignored —
        # token verification is the trust mechanism now.
        return [
            {
                "name": p.name,
                "address": p.address,
                "port": p.port,
                "agents": p.agents,
                "active_agents": p.active_agents,
                "connected": True,
                "last_seen": p.last_seen,
            }
            for p in self.peers.values()
        ]


# ============================================================
# Main daemon
# ============================================================

class AgentRelay:
    def __init__(self, cfg: Config, config_path: Path | None = None):
        self.cfg = cfg
        self.config_path = config_path or DEFAULT_CONFIG
        self.peers = PeerRegistry()
        self.talk = ConversationStore()
        self.pairing = PairingManager()
        self.agent_data = AgentDataStore()
        self.idea_store = IdeaStore()
        self.bug_store = BugStore()
        self.azc: AsyncZeroconf | None = None
        self.browser: AsyncServiceBrowser | None = None
        self.service_info: ServiceInfo | None = None
        self._heartbeat_event: asyncio.Event | None = None
        self._udp_transport: asyncio.DatagramTransport | None = None
        from relay_client import log_agent_availability

        log_agent_availability(cfg)

    def _agent_availability_payload(self) -> dict[str, list[dict]]:
        from relay_client import available_agent_labels, unavailable_agent_labels

        return {
            "agents": available_agent_labels(self.cfg),
            "agents_missing": unavailable_agent_labels(self.cfg),
            "active_agents": list_active_agent_names(),
        }

    def _agentmemory_cfg(self):
        from agentmemory_bridge import AgentmemoryConfig

        cfg = getattr(self.cfg, "agentmemory", None)
        if isinstance(cfg, AgentmemoryConfig):
            return cfg
        return AgentmemoryConfig()

    async def _agentmemory_recall_for_agent(self, agent_id: str) -> str:
        from agentmemory_bridge import fetch_recall_context

        am = self._agentmemory_cfg()
        if not am.enabled:
            return ""
        query = (
            f"AgentRelay {agent_id} project context architecture "
            f"preferences on node {self.cfg.node_name}"
        )
        return await fetch_recall_context(am, query=query, agent_id=agent_id)

    async def _agentmemory_on_pty_close(
        self, session: PTYSession, reason: str,
    ) -> None:
        from agentmemory_bridge import observe_session_end

        am = self._agentmemory_cfg()
        if not am.enabled or session.session_type != "agent":
            return
        await observe_session_end(
            am,
            agent_id=session.agent_name,
            session_id=session.session_id,
            reason=reason,
            scrollback=session.scrollback_text(),
            node_name=self.cfg.node_name,
            uptime_seconds=session.uptime,
        )

    def _register_agentmemory_close_hook(self, session: PTYSession) -> None:
        am = self._agentmemory_cfg()
        if not am.enabled or not am.observe_on_close:
            return
        if session.session_type != "agent":
            return

        def _hook(_sid: str, reason: str) -> None:
            asyncio.ensure_future(self._agentmemory_on_pty_close(session, reason))

        session.chain_on_close(_hook)

    async def _agentmemory_status(self) -> dict[str, Any]:
        from agentmemory_bridge import health_ok

        am = self._agentmemory_cfg()
        if not am.enabled:
            return {"enabled": False, "reachable": False}
        reachable = await health_ok(am)
        return {
            "enabled": True,
            "reachable": reachable,
            "url": am.url,
            "project": am.project,
        }

    def _peer_announcement_payload(self) -> dict[str, Any]:
        from relay_client import is_adapter_available

        installed = ",".join(
            name for name, spec in self.cfg.adapters.items()
            if is_adapter_available(name, spec)
        )
        active = ",".join(list_active_agent_names())
        return {
            "node": self.cfg.node_name,
            "address": self._local_ip(),
            "port": self.cfg.port,
            "agents": installed,
            "active_agents": active,
            "machine_id": get_machine_id(),
            "token_hash": _token_hash(self.cfg.token),
        }

    async def register_mdns(self) -> None:
        self.azc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        addresses = [socket.inet_aton(self._local_ip())]
        payload = self._peer_announcement_payload()
        agent_ids = payload["agents"]
        active_ids = payload["active_agents"]
        self.service_info = ServiceInfo(
            type_=SERVICE_TYPE,
            name=f"{self.cfg.node_name}.{SERVICE_TYPE}",
            addresses=addresses,
            port=self.cfg.port,
            properties={
                "node": self.cfg.node_name,
                "version": "0.2.0",
                "agents": agent_ids,
                "active": active_ids,
            },
            server=f"{self.cfg.node_name}.local.",
        )
        await self.azc.async_register_service(self.service_info)
        log.info("mDNS registered: %s on port %d",
                 self.cfg.node_name, self.cfg.port)
        self.browser = AsyncServiceBrowser(
            self.azc.zeroconf, [SERVICE_TYPE],
            handlers=[self._on_service_state_change],
        )

    def _local_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    def _on_service_state_change(self, zc=None, service_type=None, name=None,
                                  state_change=None, **kwargs) -> None:
        name = name or kwargs.get("name")
        state_change = state_change or kwargs.get("state_change")
        if not name or state_change is None:
            return
        asyncio.ensure_future(self._resolve_peer(name, state_change))

    async def _resolve_peer(self, name: str,
                            state_change: ServiceStateChange) -> None:
        if state_change == ServiceStateChange.Removed:
            self.peers.remove(name.split(".")[0])
            return
        info = AsyncServiceInfo(SERVICE_TYPE, name)
        if not await info.async_request(self.azc.zeroconf, 3000):
            return
        node = info.properties.get(b"node", b"").decode() or name.split(".")[0]
        if node == self.cfg.node_name:
            return  # ourselves
        addrs = info.parsed_scoped_addresses()
        agents = info.properties.get(b"agents", b"").decode()
        active = info.properties.get(b"active", b"").decode()
        if addrs:
            self.peers.upsert(
                node, addrs[0], info.port, agents=agents, active_agents=active)

    async def _announce_to_peer(self, addr: str, port: int) -> None:
        """Tell a specific peer our address so they keep us in their registry."""
        payload = self._peer_announcement_payload()
        url = f"http://{addr}:{port}/peer-announce"
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5))
        except Exception:
            pass

    async def start_udp_discovery(self) -> None:
        """Bind a UDP socket for LAN broadcast peer discovery."""
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _DiscoveryProtocol(self),
                local_addr=("0.0.0.0", self.cfg.port),
                allow_broadcast=True,
            )
            self._udp_transport = transport
            log.info("UDP discovery listening on port %d (UDP)", self.cfg.port)
        except Exception as exc:
            log.warning("UDP discovery unavailable: %s", exc)

    def _udp_broadcast(self) -> None:
        """Send a UDP broadcast so any AgentRelay peer on the LAN can discover us."""
        if self._udp_transport is None:
            return
        payload = self._peer_announcement_payload()
        try:
            self._udp_transport.sendto(
                json.dumps(payload).encode(),
                (DISCOVERY_BROADCAST, self.cfg.port),
            )
        except Exception as exc:
            log.debug("UDP broadcast failed: %s", exc)

    def _trigger_heartbeat(self) -> None:
        """Signal the heartbeat loop to fire immediately (e.g. after a PTY change)."""
        if self._heartbeat_event is not None:
            self._heartbeat_event.set()

    async def _heartbeat_loop(self, stop: asyncio.Event) -> None:
        """Re-announce to all peers every 30s, or immediately when _trigger_heartbeat is called."""
        self._heartbeat_event = asyncio.Event()
        while not stop.is_set():
            self._udp_broadcast()
            for peer in list(self.peers.peers.values()):
                await self._announce_to_peer(peer.address, peer.port)
            self._heartbeat_event.clear()
            done, _ = await asyncio.wait(
                [asyncio.ensure_future(stop.wait()),
                 asyncio.ensure_future(self._heartbeat_event.wait())],
                timeout=30,
                return_when=asyncio.FIRST_COMPLETED,
            )

    async def shutdown(self) -> None:
        log.info("shutting down")
        if self._udp_transport is not None:
            self._udp_transport.close()
        if self.browser:
            await self.browser.async_cancel()
        if self.azc and self.service_info:
            await self.azc.async_unregister_service(self.service_info)
            await self.azc.async_close()

    # ---- HTTP handlers ----

    def _token_from_request(self, request: web.Request) -> str:
        header = request.headers.get("X-Agent-Token", "")
        if header:
            return header
        return request.rel_url.query.get("token", "")

    def _auth(self, request: web.Request) -> bool:
        return secrets.compare_digest(
            self._token_from_request(request), self.cfg.token)

    def reload_config(self) -> None:
        if self.config_path.exists():
            self.cfg = Config.load(self.config_path)

    def _localhost(self, request: web.Request) -> bool:
        return request.remote in ("127.0.0.1", "::1", "localhost")

    async def handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "node": self.cfg.node_name})

    async def handle_pending_deliveries(self, request: web.Request) -> web.Response:
        """Return and clear queued GUI deliveries. Localhost-only, no auth needed."""
        if request.remote not in ("127.0.0.1", "::1"):
            return web.json_response({"error": "localhost only"}, status=403)
        items = list(_gui_delivery_queue)
        _gui_delivery_queue.clear()
        return web.json_response({"deliveries": items})

    async def handle_peer_announce(self, request: web.Request) -> web.Response:
        """A remote peer calls this to register/refresh itself in our registry."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        node = body.get("node", "")
        addr = body.get("address", request.remote)
        port = int(body.get("port", 9876))
        agents = body.get("agents", "")
        active_agents = body.get("active_agents", "")
        machine_id = body.get("machine_id", "")
        token_hash = body.get("token_hash", "")
        if token_hash and not secrets.compare_digest(
            token_hash, _token_hash(self.cfg.token)
        ):
            return web.json_response({"error": "unauthorized"}, status=401)
        if node and node != self.cfg.node_name:
            self.peers.upsert(
                node, addr, port, agents=agents, active_agents=active_agents)
            store = get_ssh_store()
            existing_by_id = store.get_by_machine_id(machine_id) if machine_id else None
            existing_by_name = store.get(node)
            if existing_by_id and existing_by_id.node_name != node:
                # machine_id matches a preset with a different node_name → drift
                _pending_ssh_presets.append({
                    "type": "rename",
                    "old_node_name": existing_by_id.node_name,
                    "new_node_name": node,
                    "host": addr,
                    "machine_id": machine_id,
                })
            elif not existing_by_name and not existing_by_id:
                # New peer with no preset at all
                already = any(p.get("node_name") == node for p in _pending_ssh_presets)
                if not already:
                    _pending_ssh_presets.append({
                        "type": "new",
                        "node_name": node,
                        "host": addr,
                        "machine_id": machine_id,
                    })
        return web.json_response({"ok": True})

    async def handle_inbox(self, request: web.Request) -> web.Response:
        """Return recent incoming dispatches. Localhost-only or authenticated."""
        if not self._localhost(request) and not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        since = float(request.rel_url.query.get("since", 0))
        from_node = request.rel_url.query.get("from", "")
        items = [
            m for m in _dispatch_inbox
            if m["ts"] > since and (not from_node or m["from"] == from_node)
        ]
        return web.json_response({"messages": items})

    async def handle_info(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        from relay_client import is_adapter_available

        adapters = {}
        for name, spec in self.cfg.adapters.items():
            if not is_adapter_available(name, spec):
                continue
            entry: dict = {"mode": spec.mode, "label": spec.label or name}
            if spec.role:
                entry["role"] = spec.role
            if spec.capabilities:
                entry["capabilities"] = spec.capabilities
            adapters[name] = entry
        active_sessions = [s["agent"] for s in pty_registry.list() if s["alive"]]
        return web.json_response({
            "node": self.cfg.node_name,
            "port": self.cfg.port,
            "adapters": adapters,
            "active_agents": list_active_agent_names(),
            "rules": [r.__dict__ for r in self.cfg.rules],
            "active_sessions": active_sessions,
        })

    async def handle_peers(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({
            "peers": self.peers.list(),
        })

    async def handle_setup(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({
            "node": self.cfg.node_name,
            "address": self._local_ip(),
            "port": self.cfg.port,
            **self._agent_availability_payload(),
            "wait_before_send_seconds": self.cfg.wait_before_send_seconds,
            "nearby": self.peers.list(),
        })

    async def handle_forward(self, request: web.Request) -> web.Response:
        """Forward a request so it appears in the other computer's agent window."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        from_node = body.get("from_node", "unknown")
        from_agent = body.get("from_agent", "")
        requested_agent = body.get("to_agent") or self.cfg.default_agent
        permission_profile = (body.get("permission_profile") or "safe").strip()
        active = list_active_agent_names()
        to_agent = self.cfg.resolve_adapter_name(
            requested_agent, prefer_interactive=True, active_agents=active or None)
        message = (body.get("message") or "").strip()
        originator_task_id: str | None = body.get("task_id")
        # Prefer explicit reply_to; fall back to deriving from request.remote so
        # the originator doesn't need to know its own external IP.
        reply_to: str | None = body.get("reply_to") or (
            f"http://{request.remote}:{self.cfg.port}"
            f"/api/tasks/{originator_task_id}/status"
            if originator_task_id else None
        )

        if not message:
            return web.json_response({"error": "missing message"}, status=400)
        if not to_agent:
            if active:
                return web.json_response({
                    "ok": False,
                    "error": (
                        f"Agent '{requested_agent}' is not running on "
                        f"{self.cfg.node_name}. Active terminals: "
                        f"{', '.join(active)}"
                    ),
                    "requested_agent": requested_agent,
                    "active_agents": active,
                }, status=200)
            return web.json_response(
                {"error": f"unknown agent: {requested_agent}"}, status=400)

        adapter = self.cfg.adapters[to_agent]
        if adapter.mode not in INTERACTIVE_MODES:
            talk_cfg = dataclasses.replace(self.cfg, use_tmux=False)
            result = await spawn_agent(talk_cfg, adapter, message)
        else:
            header = (
                f"[Forwarded from {from_agent} on {from_node}]\n\n"
                if from_agent else ""
            )
            result = await spawn_agent(
                self.cfg, adapter, header + message)

        import time as _time
        _dispatch_inbox.append({
            "request_id": uuid.uuid4().hex,
            "from": from_node,
            "agent": to_agent,
            "command": message,
            "ts": _time.time(),
        })
        if len(_dispatch_inbox) > _INBOX_MAX:
            _dispatch_inbox.pop(0)

        # Create a receiver-side task record so both machines track state.
        tq = get_task_queue()
        local_task_id = await tq.create(
            source_node=from_node,
            source_agent=from_agent or None,
            target_node=self.cfg.node_name,
            target_agent=to_agent,
            message=message,
            status="received",
            permission_profile=permission_profile,
            originator_task_id=originator_task_id,
            reply_to=reply_to,
        )

        # If the message landed in an interactive PTY, record the session and
        # register a close callback that pushes /status back to the originator.
        pty_session = _find_pty_for_adapter(to_agent)
        if pty_session:
            await tq.mark_running(local_task_id, session_id=pty_session.session_id)

            if reply_to and originator_task_id:
                _oti = originator_task_id
                _rt = reply_to
                _ltid = local_task_id

                def _on_pty_close(sid: str, reason: str) -> None:
                    asyncio.ensure_future(
                        _on_session_closed(tq, _ltid, _oti, _rt, reason))

                pty_session._on_close = _on_pty_close

        notify("AgentRelay",
               f"Request from {from_node}: {message[:50]}")
        ok = result.get("exit_code", 1) == 0 or result.get("status") in (
            "sent", "queued", "spawned")
        full_message = (header if adapter.mode in INTERACTIVE_MODES else "") + message
        forwarded_byte_count = len(full_message.encode("utf-8"))
        return web.json_response({
            "ok": ok,
            "node": self.cfg.node_name,
            "agent": to_agent,
            "task_id": local_task_id,
            "delivery": "forward",
            "requested_agent": requested_agent,
            "resolved_agent": to_agent,
            "byte_count": len(message.encode("utf-8")),
            "forwarded_byte_count": forwarded_byte_count,
            **result,
        })

    # ------------------------------------------------------------------
    # Task queue API
    # ------------------------------------------------------------------

    async def handle_tasks_list(self, request: web.Request) -> web.Response:
        """GET /api/tasks — list tasks. Localhost-only or authenticated."""
        if not self._localhost(request) and not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        qs = request.rel_url.query
        tasks = await get_task_queue().list_tasks(
            status=qs.get("status") or None,
            target_node=qs.get("target_node") or None,
            source_node=qs.get("source_node") or None,
            limit=int(qs.get("limit", 100)),
            since=float(qs.get("since", 0)),
        )
        return web.json_response({"tasks": tasks})

    async def handle_task_get(self, request: web.Request) -> web.Response:
        """GET /api/tasks/{id} — get one task. Localhost-only."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        task = await get_task_queue().get(request.match_info["id"])
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(task)

    async def handle_task_status(self, request: web.Request) -> web.Response:
        """POST /api/tasks/{id}/status — receive a status callback from a peer."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        task_id = request.match_info["id"]
        status = body.get("status", "")
        if not status:
            return web.json_response({"error": "missing status"}, status=400)
        tq = get_task_queue()
        ok = await tq.update_status(
            task_id, status,
            result=body.get("result"),
            error=body.get("error"),
        )
        if not ok:
            task = await tq.get(task_id)
            if not task:
                return web.json_response({"error": "not found"}, status=404)
            return web.json_response(
                {"error": f"invalid transition from '{task['status']}' to '{status}'"}, status=409)
        _notify_task_event(task_id, status)
        return web.json_response({"ok": True, "task_id": task_id, "status": status})

    async def handle_task_events(self, request: web.Request) -> web.StreamResponse:
        """GET /api/tasks/events — SSE stream. Localhost-only. Pushes on any task state change."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        resp = web.StreamResponse()
        resp.headers["Content-Type"] = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        await resp.prepare(request)
        q: asyncio.Queue = asyncio.Queue()
        _task_event_queues.append(q)
        try:
            # Send a keep-alive comment every 15 s so the browser doesn't time out.
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15)
                    await resp.write(
                        f"data: {json.dumps(payload)}\n\n".encode())
                except asyncio.TimeoutError:
                    await resp.write(b": keep-alive\n\n")
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            try:
                _task_event_queues.remove(q)
            except ValueError:
                pass
        return resp

    async def handle_pair_request(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        from_node = body.get("from_node", "").strip()
        if not from_node:
            return web.json_response({"error": "from_node required"}, status=400)
        addr = request.remote or "unknown"
        req = self.pairing.request(from_node, addr)
        notify("AgentRelay", f"{from_node} wants to connect")
        return web.json_response({"request_id": req.id, "status": "pending"})

    async def handle_pair_pending(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({"pending": self.pairing.list_pending()})

    async def handle_pair_approve(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        rid = body.get("request_id", "")
        if not self.pairing.approve(rid, self.cfg.token, self.cfg.node_name):
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"ok": True})

    async def handle_pair_reject(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        self.pairing.reject(body.get("request_id", ""))
        return web.json_response({"ok": True})

    async def handle_pair_poll(self, request: web.Request) -> web.Response:
        from_node = request.query.get("from_node", "")
        if not from_node:
            return web.json_response({"error": "from_node required"}, status=400)
        result = self.pairing.poll(from_node)
        if not result:
            return web.json_response({"status": "pending"})
        return web.json_response({
            "status": "connected",
            "token": result["token"],
            "node_name": result["node_name"],
        })

    async def handle_dispatch(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        command = body.get("command")
        sender = body.get("from", "unknown")
        agent_hint = body.get("agent")
        policy_hint = body.get("policy_hint")
        request_id = body.get("request_id") or uuid.uuid4().hex

        if not command:
            return web.json_response({"error": "missing command"}, status=400)

        # If caller named an agent but didn't give an explicit policy,
        # treat as "agent" action.
        if agent_hint and policy_hint is None:
            policy_hint = "agent"

        action, agent_name = decide(self.cfg, command, policy_hint)
        if action == "agent" and agent_hint:
            agent_name = agent_hint

        log.info("[%s] from=%s action=%s agent=%s cmd=%r",
                 request_id, sender, action, agent_name, command)
        notify("agentrelay", f"{action} from {sender}: {command[:80]}")

        # Store in inbox so local skills can poll for replies.
        import time as _time
        _dispatch_inbox.append({
            "request_id": request_id,
            "from": sender,
            "agent": agent_name,
            "command": command,
            "ts": _time.time(),
        })
        if len(_dispatch_inbox) > _INBOX_MAX:
            _dispatch_inbox.pop(0)

        result: dict[str, Any]
        if action == "reject":
            result = {"status": "rejected", "exit_code": 1,
                      "stdout": "", "stderr": "policy: reject"}
        elif action == "auto":
            result = await auto_execute(command)
        elif action == "agent":
            if not agent_name or agent_name not in self.cfg.adapters:
                result = {"status": "error", "exit_code": 1,
                          "stdout": "",
                          "stderr": f"unknown agent: {agent_name}"}
            else:
                result = await spawn_agent(
                    self.cfg, self.cfg.adapters[agent_name], command)
        elif action == "approve":
            loop = asyncio.get_running_loop()
            approved = await loop.run_in_executor(
                None, approve_dialog, self.cfg, sender, command)
            if not approved:
                result = {"status": "rejected", "exit_code": 1,
                          "stdout": "", "stderr": "user rejected"}
            elif agent_name and agent_name in self.cfg.adapters:
                result = await spawn_agent(
                    self.cfg, self.cfg.adapters[agent_name], command)
            else:
                result = await auto_execute(command)
        else:
            result = {"status": "error", "exit_code": 1,
                      "stdout": "", "stderr": f"unknown action: {action}"}

        return web.json_response({
            "request_id": request_id,
            "node": self.cfg.node_name,
            "action": action,
            "agent": agent_name,
            **result,
        })

    async def handle_talk(self, request: web.Request) -> web.Response:
        """Agent-to-agent message: run local agent with thread context, return reply."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        from_node = body.get("from_node")
        from_agent = body.get("from_agent")
        to_agent = body.get("to_agent") or self.cfg.default_agent
        message = (body.get("message") or "").strip()
        thread_id = body.get("thread_id")

        if not from_node or not from_agent:
            return web.json_response(
                {"error": "from_node and from_agent required"}, status=400)
        if not message:
            return web.json_response({"error": "missing message"}, status=400)
        if not to_agent or to_agent not in self.cfg.adapters:
            return web.json_response(
                {"error": f"unknown agent: {to_agent}"}, status=400)

        local_node = self.cfg.node_name
        log.info("talk from %s@%s -> %s thread=%s: %r",
                 from_agent, from_node, to_agent, thread_id, message[:80])
        notify("agentrelay talk",
               f"{from_agent}@{from_node} → {to_agent}: {message[:60]}")

        pre_messages = self.talk.get_messages(thread_id) if thread_id else []
        user_msg = self.talk.append(
            thread_id,
            local_node=local_node,
            peer_node=from_node,
            local_agent=to_agent,
            remote_agent=from_agent,
            remote_node=from_node,
            from_node=from_node,
            from_agent=from_agent,
            to_node=local_node,
            to_agent=to_agent,
            role="user",
            content=message,
        )
        tid = user_msg.thread_id

        prompt = self.talk.format_prompt(
            tid,
            local_node=local_node,
            from_node=from_node,
            from_agent=from_agent,
            new_message=message,
            _messages=pre_messages,
        )

        talk_cfg = dataclasses.replace(self.cfg, use_tmux=False)
        result = await spawn_agent(
            talk_cfg, self.cfg.adapters[to_agent], prompt)

        reply_content = (result.get("stdout") or "").strip()
        if not reply_content:
            reply_content = (result.get("stderr") or "").strip()

        assistant_msg = self.talk.append(
            tid,
            local_node=local_node,
            peer_node=from_node,
            local_agent=to_agent,
            remote_agent=from_agent,
            remote_node=from_node,
            from_node=local_node,
            from_agent=to_agent,
            to_node=from_node,
            to_agent=from_agent,
            role="assistant",
            content=reply_content,
        )

        ok = result.get("exit_code", 1) == 0
        return web.json_response({
            "ok": ok,
            "thread_id": tid,
            "message_id": user_msg.id,
            "reply": {
                "id": assistant_msg.id,
                "from_node": local_node,
                "from_agent": to_agent,
                "to_node": from_node,
                "to_agent": from_agent,
                "content": reply_content,
            },
            "exit_code": result.get("exit_code"),
            "status": result.get("status"),
        })

    async def handle_coordinate(self, request: web.Request) -> web.Response:
        """Fan a task out to multiple agents, collect results, optionally synthesize."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        task = (body.get("task") or "").strip()
        agents = body.get("agents") or []
        coordinator_agent = body.get("coordinator_agent") or self.cfg.default_agent
        mode = body.get("mode", "parallel")
        thread_id = body.get("thread_id")

        if not task:
            return web.json_response({"error": "missing task"}, status=400)
        if not agents:
            return web.json_response({"error": "missing agents"}, status=400)
        if mode not in ("parallel", "sequential"):
            return web.json_response({"error": "mode must be parallel or sequential"}, status=400)

        local_node = self.cfg.node_name

        async def _enrich(entry: dict) -> dict:
            """Add role/capabilities from /info if not supplied by caller."""
            entry = dict(entry)
            if "role" in entry and "capabilities" in entry:
                return entry
            node, agent = entry.get("node", local_node), entry.get("agent", "")
            if node == local_node:
                spec = self.cfg.adapters.get(agent)
                if spec:
                    entry.setdefault("role", spec.role or "")
                    entry.setdefault("capabilities", spec.capabilities or [])
            else:
                peer = self.peers.peers.get(node)
                if peer:
                    try:
                        t = aiohttp.ClientTimeout(total=3)
                        async with aiohttp.ClientSession(timeout=t) as s:
                            async with s.get(
                                f"http://{peer.address}:{peer.port}/info",
                                headers={"X-Agent-Token": self.cfg.token},
                            ) as r:
                                if r.status == 200:
                                    info = await r.json()
                                    spec = (info.get("adapters") or {}).get(agent, {})
                                    entry.setdefault("role", spec.get("role", ""))
                                    entry.setdefault("capabilities", spec.get("capabilities", []))
                    except Exception:
                        pass
            entry.setdefault("role", "")
            entry.setdefault("capabilities", [])
            return entry

        async def _call_agent(entry: dict, message: str) -> dict:
            node = entry.get("node", local_node)
            agent = entry["agent"]
            role = entry.get("role", "")
            caps = entry.get("capabilities", [])
            if node == local_node:
                if agent not in self.cfg.adapters:
                    return {"node": node, "agent": agent, "role": role,
                            "capabilities": caps, "content": "",
                            "error": f"unknown local agent: {agent}"}
                talk_cfg = dataclasses.replace(self.cfg, use_tmux=False)
                result = await spawn_agent(talk_cfg, self.cfg.adapters[agent], message)
                content = (result.get("stdout") or "").strip()
                if not content:
                    content = (result.get("stderr") or "").strip()
                return {"node": node, "agent": agent, "role": role,
                        "capabilities": caps, "content": content,
                        "exit_code": result.get("exit_code")}
            else:
                peer = self.peers.peers.get(node)
                if not peer:
                    return {"node": node, "agent": agent, "role": role,
                            "capabilities": caps, "content": "",
                            "error": f"peer not found: {node}"}
                try:
                    payload = {
                        "thread_id": thread_id,
                        "from_node": local_node,
                        "from_agent": coordinator_agent,
                        "to_agent": agent,
                        "message": message,
                    }
                    t = aiohttp.ClientTimeout(total=None, sock_connect=5)
                    async with aiohttp.ClientSession(timeout=t) as s:
                        async with s.post(
                            f"http://{peer.address}:{peer.port}/talk",
                            json=payload,
                            headers={"X-Agent-Token": self.cfg.token},
                        ) as r:
                            data = await r.json()
                    content = (data.get("reply") or {}).get("content") or ""
                    return {"node": node, "agent": agent, "role": role,
                            "capabilities": caps, "content": content,
                            "thread_id": data.get("thread_id")}
                except Exception as e:
                    return {"node": node, "agent": agent, "role": role,
                            "capabilities": caps, "content": "", "error": str(e)}

        def _role_prefix(entry: dict) -> str:
            role = entry.get("role", "")
            caps = entry.get("capabilities", [])
            if not role and not caps:
                return ""
            caps_str = ", ".join(caps) if caps else "general"
            return f"[Role: {role} | Capabilities: {caps_str}]\n\n"

        # Enrich all entries with role/capabilities
        agents = await asyncio.gather(*[_enrich(a) for a in agents])

        # Fan out
        agent_results: list[dict]
        if mode == "sequential":
            agent_results = []
            for entry in agents:
                prior = "\n".join(
                    f"[{r['agent']}@{r['node']}]: {r['content']}"
                    for r in agent_results if r.get("content")
                )
                context = f"\n\nContext from prior agents:\n{prior}" if prior else ""
                message = _role_prefix(entry) + task + context
                agent_results.append(await _call_agent(entry, message))
        else:
            tasks = [_call_agent(e, _role_prefix(e) + task) for e in agents]
            agent_results = list(await asyncio.gather(*tasks))

        # Synthesis (skipped when coordinator_agent is None — broadcast mode)
        synthesis: str | None = None
        if coordinator_agent and coordinator_agent in self.cfg.adapters:
            lines = [
                "You are coordinating a multi-agent task via AgentRelay.",
                f"Original task: {task}", "",
                "Results from each agent:",
            ]
            for r in agent_results:
                role_tag = f" ({r['role']})" if r.get("role") else ""
                lines.append(f"\n[{r['agent']}@{r['node']}{role_tag}]:")
                lines.append(r.get("content") or r.get("error") or "(no response)")
            lines += ["", "Synthesize these results into a coherent, actionable response."]
            talk_cfg = dataclasses.replace(self.cfg, use_tmux=False)
            synth = await spawn_agent(
                talk_cfg, self.cfg.adapters[coordinator_agent], "\n".join(lines))
            synthesis = (synth.get("stdout") or "").strip() or None

        thread_ids = [r["thread_id"] for r in agent_results if r.get("thread_id")]
        return web.json_response({
            "coordinator": {"node": local_node, "agent": coordinator_agent},
            "thread_id": thread_ids[0] if thread_ids else None,
            "mode": mode,
            "agent_results": agent_results,
            "synthesis": synthesis,
        })

    async def handle_talk_threads(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({"threads": self.talk.list_threads()})

    async def handle_talk_thread(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        thread_id = request.match_info.get("thread_id", "")
        messages = [m.to_dict() for m in self.talk.get_messages(thread_id)]
        if not messages:
            return web.json_response({"error": "thread not found"}, status=404)
        return web.json_response({"thread_id": thread_id, "messages": messages})

    # ---- /terminal WebSocket handler ----

    async def handle_terminal(self, request: web.Request) -> web.WebSocketResponse:
        """
        WebSocket endpoint for embedded terminal sessions.

        Protocol frames (JSON):
          open   → create/attach session, returns open_ack with write_token (owner)
                   or null write_token (remote viewer)
          input  → send keystrokes, requires write_token
          resize → resize PTY, requires write_token; viewers adjust client-side only
          close  → terminate session, requires write_token

        Auth: X-Agent-Token header required (same token as all other endpoints).
        """
        if not self._auth(request):
            return web.Response(status=401, text="unauthorized")

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session: PTYSession | None = None

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        frame = json.loads(msg.data)
                    except json.JSONDecodeError:
                        await ws.send_str(json.dumps(
                            {"type": "error", "session_id": None,
                             "code": "parse_error", "message": "invalid JSON"}))
                        continue

                    ftype = frame.get("type")
                    sid = frame.get("session_id")

                    if ftype == "open":
                        agent = frame.get("agent", "claude")
                        cols = int(frame.get("cols", 220))
                        rows = int(frame.get("rows", 50))
                        session_type = (
                            frame.get("session_type")
                            or frame.get("kind")
                            or ("ssh" if frame.get("ssh_node") else "agent")
                        )

                        if sid:
                            # Re-attach to existing session
                            session = pty_registry.get(sid)
                            if not session:
                                await ws.send_str(json.dumps(
                                    {"type": "error", "session_id": sid,
                                     "code": "session_not_found",
                                     "message": f"no session {sid}"}))
                                continue
                            # Remote viewer — no write_token
                            await session.subscribe(ws, owner=False)
                        elif session_type == "ssh":
                            node_name = (frame.get("ssh_node") or "").strip()
                            if not node_name:
                                await ws.send_str(json.dumps(
                                    {"type": "error", "session_id": None,
                                     "code": "ssh_preset_required",
                                     "message": "ssh_node is required"}))
                                continue
                            store = get_ssh_store()
                            ssh_host = store.get(node_name)
                            if not ssh_host:
                                await ws.send_str(json.dumps(
                                    {"type": "error", "session_id": None,
                                     "code": "ssh_preset_not_found",
                                     "message": f"no SSH preset for '{node_name}'"}))
                                continue

                            reuse = bool(frame.get("reuse", False))
                            session = (
                                pty_registry.find_alive_by_ssh_node(node_name)
                                if reuse else None
                            )
                            created_session = False
                            if not session:
                                from relay_client import validate_launch_argv

                                argv = build_ssh_shell_argv(ssh_host)
                                path_err = validate_launch_argv(argv)
                                if path_err:
                                    await ws.send_str(json.dumps(
                                        {"type": "error", "session_id": None,
                                         "code": "spawn_failed",
                                         "message": path_err}))
                                    continue

                                session = PTYSession(
                                    agent_name=f"ssh:{node_name}",
                                    node=self.cfg.node_name,
                                    cols=cols,
                                    rows=rows,
                                    session_type="ssh",
                                    target=node_name,
                                )
                                pty_registry.register(session)
                                created_session = True
                                try:
                                    await session.start(argv)
                                except Exception as exc:
                                    created_session = False
                                    pty_registry.remove(session.session_id)
                                    session = None
                                    log.warning(
                                        "SSH PTY spawn failed for %s %s: %s",
                                        node_name, describe_ssh_argv(argv), exc)
                                    await ws.send_str(json.dumps(
                                        {"type": "error", "session_id": None,
                                         "code": "spawn_failed",
                                         "message": (
                                             f"Could not start SSH shell for "
                                             f"{node_name}: {exc}"
                                         )}))
                                    continue
                            await session.subscribe(
                                ws,
                                owner=True,
                                include_scrollback=reuse,
                                extra_ack={
                                    "new_session": created_session,
                                    "session_type": "ssh",
                                    "ssh_node": node_name,
                                },
                            )
                        else:
                            resolved = self.cfg.resolve_adapter_name(
                                agent, prefer_interactive=True)
                            if not resolved:
                                await ws.send_str(json.dumps(
                                    {"type": "error", "session_id": None,
                                     "code": "agent_not_found",
                                     "message": f"no adapter for agent '{agent}'"}))
                                continue
                            agent = resolved
                            adapter = self.cfg.adapters[agent]
                            reuse = bool(frame.get("reuse", False))
                            session = None
                            created_session = False
                            if reuse:
                                session = pty_registry.find_alive_by_agent(agent)
                            else:
                                existing = pty_registry.find_alive_by_agent(agent)
                                if existing:
                                    await existing.stop()
                                    pty_registry.remove(existing.session_id)
                                    self._trigger_heartbeat()
                            if not session:
                                from relay_client import (
                                    interactive_launch_argv,
                                    validate_launch_argv,
                                )

                                yolo = bool(frame.get("yolo", False))
                                profile = frame.get("profile")
                                resume_session_id = frame.get("resume_session_id") or None
                                argv = interactive_launch_argv(
                                    agent, adapter, yolo=yolo, profile=profile,
                                    resume_session_id=resume_session_id)
                                path_err = validate_launch_argv(argv)
                                if path_err:
                                    await ws.send_str(json.dumps(
                                        {"type": "error", "session_id": None,
                                         "code": "spawn_failed",
                                         "message": path_err}))
                                    continue

                                session = PTYSession(
                                    agent_name=agent,
                                    node=self.cfg.node_name,
                                    cols=cols,
                                    rows=rows,
                                )
                                pty_registry.register(session)
                                self._register_agentmemory_close_hook(session)
                                self._trigger_heartbeat()
                                created_session = True
                                try:
                                    await session.start(argv)
                                except Exception as exc:
                                    created_session = False
                                    pty_registry.remove(session.session_id)
                                    self._trigger_heartbeat()
                                    session = None
                                    log.warning(
                                        "PTY spawn failed for %s %r: %s",
                                        agent, argv, exc)
                                    await ws.send_str(json.dumps(
                                        {"type": "error", "session_id": None,
                                         "code": "spawn_failed",
                                         "message": (
                                             f"Could not start {agent}: {exc}"
                                         )}))
                                    continue
                            await session.subscribe(
                                ws,
                                owner=True,
                                include_scrollback=reuse,
                                extra_ack={
                                    "new_session": created_session,
                                    "session_type": "agent",
                                },
                            )
                            if created_session and frame.get("inject_snippet"):
                                asyncio.create_task(
                                    self._inject_agent_snippet(session))

                    elif ftype == "input":
                        if not session:
                            continue
                        token = frame.get("write_token", "")
                        data_b64 = frame.get("data", "")
                        try:
                            data = base64.b64decode(data_b64).decode("utf-8", errors="replace")
                            await session.write(data, token)
                        except PermissionError:
                            await ws.send_str(json.dumps(
                                {"type": "error", "session_id": session.session_id,
                                 "code": "unauthorized",
                                 "message": "invalid write_token"}))
                        except EOFError as exc:
                            await ws.send_str(json.dumps(
                                {"type": "error", "session_id": session.session_id,
                                 "code": "pty_error", "message": str(exc)}))
                        except Exception as exc:
                            log.warning(
                                "terminal input failed for %s: %s",
                                session.session_id, exc)

                    elif ftype == "resize":
                        if not session:
                            continue
                        token = frame.get("write_token", "")
                        cols = int(frame.get("cols", session.cols))
                        rows = int(frame.get("rows", session.rows))
                        try:
                            await session.resize(cols, rows, token)
                        except PermissionError:
                            await ws.send_str(json.dumps(
                                {"type": "error", "session_id": session.session_id,
                                 "code": "unauthorized",
                                 "message": "invalid write_token"}))

                    elif ftype == "close":
                        if not session:
                            continue
                        token = frame.get("write_token", "")
                        if token != session.grant_write():
                            await ws.send_str(json.dumps(
                                {"type": "error", "session_id": session.session_id,
                                 "code": "unauthorized",
                                 "message": "invalid write_token"}))
                            continue
                        await session.stop()
                        pty_registry.remove(session.session_id)
                        self._trigger_heartbeat()
                        session = None

                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                    break

        finally:
            if session:
                await session.unsubscribe(ws)

        return ws

    async def _inject_agent_snippet(self, session: PTYSession) -> None:
        """Paste AgentRelay instructions into a new PTY after the shell starts."""
        from relay_client import build_agent_snippet, _fetch_nearby_agents

        try:
            nearby = await _fetch_nearby_agents(self.cfg)
        except Exception:
            nearby = []

        agent_id = session.agent_name
        raw_resume = self.agent_data.get_resume(agent_id)
        resume = None if "No resume yet" in raw_resume else raw_resume
        memory = self.agent_data.get_memory(agent_id) or None

        am_ctx = await self._agentmemory_recall_for_agent(agent_id)
        snippet = build_agent_snippet(
            self.cfg, nearby, resume=resume, memory=memory,
            agentmemory_context=am_ctx or None,
        )
        await asyncio.sleep(1.2)
        if not session.alive:
            return
        try:
            await session.write(snippet, session.grant_write())
        except Exception as exc:
            log.warning("snippet inject failed for %s: %s", session.agent_name, exc)

    # ---- GUI HTTP API (local web UI) ----

    async def handle_gui_index(self, request: web.Request) -> web.Response:
        index = gui_directory() / "index.html"
        if not index.is_file():
            return web.Response(status=404, text="GUI not installed")
        return web.FileResponse(index)

    async def handle_api_status(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        setup = {
            "relay_running": True,
            "node": self.cfg.node_name,
            "address": self._local_ip(),
            "port": self.cfg.port,
            **self._agent_availability_payload(),
            "nearby": self.peers.list(),
            "wait_before_send_seconds": self.cfg.wait_before_send_seconds,
            "agentmemory": await self._agentmemory_status(),
        }
        return web.json_response(setup)

    async def handle_api_pending(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({"pending": self.pairing.list_pending()})

    async def handle_api_agent_snippet(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        from relay_client import build_agent_snippet, _fetch_nearby_agents

        try:
            nearby = await _fetch_nearby_agents(self.cfg)
        except Exception:
            nearby = []

        agent_id = request.rel_url.query.get("agent") or self.cfg.default_agent or ""
        raw_resume = self.agent_data.get_resume(agent_id) if agent_id else ""
        resume = None if not agent_id or "No resume yet" in raw_resume else raw_resume
        memory = self.agent_data.get_memory(agent_id) or None if agent_id else None

        am_ctx = ""
        if agent_id:
            am_ctx = await self._agentmemory_recall_for_agent(agent_id)
        snippet = build_agent_snippet(
            self.cfg, nearby, resume=resume, memory=memory,
            agentmemory_context=am_ctx or None,
        )
        return web.json_response({"snippet": snippet})

    async def handle_api_approve(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        rid = body.get("request_id", "")
        peer_name = body.get("peer_name", "")
        if not self.pairing.approve(rid, self.cfg.token, self.cfg.node_name):
            return web.json_response({"error": "not found"}, status=404)
        if peer_name and self.config_path.exists():
            from config_io import load_raw, save_raw

            data = load_raw(self.config_path)
            trusted = list(set(data.get("trusted_peers") or []) | {peer_name})
            data["trusted_peers"] = trusted
            save_raw(data, self.config_path)
            self.reload_config()
        return web.json_response({"ok": True})

    async def handle_api_connect(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        peer = (body.get("peer") or "").strip()
        if not peer:
            return web.json_response({"error": "peer required"}, status=400)
        from relay_client import connect_peer

        loop = asyncio.get_running_loop()
        ok, msg = await loop.run_in_executor(
            None, connect_peer, self.cfg, self.config_path, peer)
        if ok:
            self.reload_config()
        status = 200 if ok else 400
        return web.json_response({"ok": ok, "error": None if ok else msg}, status=status)

    async def handle_api_settings(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        from config_io import update_settings

        update_settings(
            self.config_path,
            node_name=body.get("node_name"),
            wait_before_send_seconds=body.get("wait_before_send_seconds"),
        )
        self.reload_config()
        return web.json_response({"ok": True})

    def _peer_agent_ids(self, agents_field: Any) -> list[str]:
        if isinstance(agents_field, list):
            return [str(a).strip() for a in agents_field if str(a).strip()]
        return [a.strip() for a in str(agents_field or "").split(",") if a.strip()]

    def _broadcast_agent_entries(self, scope: str) -> list[dict[str, str]]:
        """Build [{node, agent}, ...] for local-only or all connected peers."""
        from relay_client import is_adapter_available

        entries = [
            {"node": self.cfg.node_name, "agent": agent_id}
            for agent_id, spec in self.cfg.adapters.items()
            if is_adapter_available(agent_id, spec)
        ]
        if scope != "all":
            return entries
        seen = {(e["node"], e["agent"]) for e in entries}
        for peer in self.peers.list():
            if not peer.get("connected"):
                continue
            node = peer.get("name", "")
            if not node or node == self.cfg.node_name:
                continue
            for agent_id in self._peer_agent_ids(peer.get("agents")):
                key = (node, agent_id)
                if key not in seen:
                    seen.add(key)
                    entries.append({"node": node, "agent": agent_id})
        return entries

    async def _deliver_broadcast(self, node: str, agent: str, message: str) -> dict:
        """Send a global broadcast message to one agent on local or remote node."""
        if node == self.cfg.node_name:
            if agent not in self.cfg.adapters:
                return {"node": node, "agent": agent, "ok": False,
                        "error": f"unknown local agent: {agent}"}
            adapter = self.cfg.adapters[agent]
            if adapter.mode in INTERACTIVE_MODES:
                result = await spawn_agent(self.cfg, adapter, message)
            else:
                talk_cfg = dataclasses.replace(self.cfg, use_tmux=False)
                result = await spawn_agent(talk_cfg, adapter, message)
            ok = result.get("exit_code", 1) == 0
            return {"node": node, "agent": agent, "ok": ok,
                    "status": result.get("status"), "stdout": result.get("stdout", "")}

        peer = self.peers.peers.get(node)
        if not peer:
            return {"node": node, "agent": agent, "ok": False,
                    "error": f"peer not found: {node}"}
        url = f"http://{peer.address}:{peer.port}/forward"
        payload = {
            "from_node": self.cfg.node_name,
            "from_agent": "agentrelay-broadcast",
            "to_agent": agent,
            "message": message,
        }
        try:
            t = aiohttp.ClientTimeout(total=None, sock_connect=5)
            async with aiohttp.ClientSession(timeout=t) as s:
                async with s.post(
                    url, json=payload, headers={"X-Agent-Token": self.cfg.token},
                ) as r:
                    data = await r.json()
            ok = r.status == 200 and data.get("ok", False)
            return {"node": node, "agent": agent, "ok": ok, "status": data.get("status")}
        except Exception as exc:
            return {"node": node, "agent": agent, "ok": False, "error": str(exc)}

    async def handle_api_broadcast(self, request: web.Request) -> web.Response:
        """Send the same global message to all agents (local, or all connected peers)."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        message = (body.get("message") or "").strip()
        scope = (body.get("scope") or "local").strip().lower()
        if not message:
            return web.json_response({"error": "message required"}, status=400)
        if scope not in ("local", "all"):
            return web.json_response(
                {"error": "scope must be 'local' or 'all'"}, status=400)

        entries = self._broadcast_agent_entries(scope)
        if not entries:
            return web.json_response({"error": "no agents configured"}, status=400)

        task = GLOBAL_BROADCAST_PREFIX + message
        results = await asyncio.gather(
            *[self._deliver_broadcast(e["node"], e["agent"], task) for e in entries])
        succeeded = sum(1 for r in results if r.get("ok"))
        return web.json_response({
            "ok": succeeded > 0,
            "global_broadcast": True,
            "scope": scope,
            "sent_to": len(entries),
            "succeeded": succeeded,
            "failed": len(entries) - succeeded,
            "results": results,
        })

    async def handle_api_send(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        agent = (body.get("agent") or "").strip()
        message = (body.get("message") or "").strip()
        local = bool(body.get("local"))
        addr = (body.get("address") or "127.0.0.1").strip()
        port = int(body.get("port") or self.cfg.port)
        permission_profile = (body.get("permission_profile") or "safe").strip()
        if not agent or not message:
            return web.json_response({"error": "agent and message required"}, status=400)
        if local:
            if agent not in self.cfg.adapters:
                return web.json_response({"error": f"unknown agent: {agent}"}, status=400)
            adapter = self.cfg.adapters[agent]
            if adapter.mode in INTERACTIVE_MODES:
                result = await spawn_agent(self.cfg, adapter, message)
            else:
                talk_cfg = dataclasses.replace(self.cfg, use_tmux=False)
                result = await spawn_agent(talk_cfg, adapter, message)
            ok = result.get("exit_code", 1) == 0
            return web.json_response({"ok": ok, **result})
        from relay_client import deliver_to_peer

        loop = asyncio.get_running_loop()
        ok, msg = await loop.run_in_executor(
            None, deliver_to_peer, self.cfg, addr, port, message, agent,
            None, None, permission_profile)
        return web.json_response({"ok": ok, "message": msg})

    async def handle_api_inbox(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        since = float(request.rel_url.query.get("since", 0))
        from_node = request.rel_url.query.get("from", "")
        items = [
            m for m in _dispatch_inbox
            if m["ts"] > since and (not from_node or m["from"] == from_node)
        ]
        return web.json_response({"messages": items})

    async def handle_api_relay_stop(self, request: web.Request) -> web.Response:
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)

        async def _shutdown() -> None:
            await asyncio.sleep(0.3)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.create_task(_shutdown())
        return web.json_response({"ok": True})

    async def handle_api_update_pull(self, request: web.Request) -> web.Response:
        """Pull latest files from git and run the install script. Localhost-only."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)

        project_root = Path(__file__).parent

        async def _run_proc(argv: list[str], timeout: int) -> tuple[int, str, str]:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
            )

        try:
            _, pull_out, pull_err = await _run_proc(["git", "pull"], timeout=30)
        except asyncio.TimeoutError:
            return web.json_response({"ok": False, "message": "Timed out while getting latest files."})
        except Exception as exc:
            return web.json_response({"ok": False, "message": f"Could not get latest files: {exc}"})

        already_current = (
            "Already up to date" in pull_out or "Already up-to-date" in pull_out
        )

        install_msg = ""
        if sys.platform == "win32":
            install_script = project_root / "install.ps1"
            install_argv = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(install_script)]
        else:
            install_script = project_root / "install.sh"
            install_argv = ["bash", str(install_script)]

        if not already_current and install_script.exists():
            try:
                _, install_out, install_err = await _run_proc(install_argv, timeout=120)
                install_msg = install_out or install_err
            except asyncio.TimeoutError:
                install_msg = "Install script timed out."
            except Exception as exc:
                install_msg = f"Install script error: {exc}"

        if already_current:
            message = "This computer already has the newest files."
        else:
            message = "Got the latest files. Restart the app to apply changes."

        return web.json_response({
            "ok": True,
            "already_current": already_current,
            "message": message,
            "detail": pull_out or pull_err,
            "install": install_msg,
        })

    async def handle_api_sessions(self, request: web.Request) -> web.Response:
        """GET /api/sessions/{agent} — list resumable sessions for an agent CLI."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        agent = request.match_info["agent"]
        sessions: list[dict] = []
        from yolo_flags import detect_agent_family
        family = detect_agent_family(agent, [agent])
        if family == "claude":
            sessions_dir = Path.home() / ".claude" / "sessions"
            if sessions_dir.is_dir():
                for f in sessions_dir.glob("*.json"):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        sessions.append({
                            "sessionId": data.get("sessionId", ""),
                            "cwd": data.get("cwd", ""),
                            "startedAt": data.get("startedAt", 0),
                            "procStart": data.get("procStart", ""),
                            "status": data.get("status", ""),
                        })
                    except Exception:
                        pass
            sessions.sort(key=lambda s: s["startedAt"], reverse=True)
        return web.json_response({"agent": agent, "sessions": sessions})

    async def handle_api_resume_get(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        agent = request.match_info["agent"]
        return web.json_response({"agent": agent, "resume": self.agent_data.get_resume(agent)})

    async def handle_api_resume_save(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        agent = request.match_info["agent"]
        try:
            self.agent_data.save_resume(agent, body.get("resume", ""))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True})

    async def handle_api_memory_get(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        agent = request.match_info["agent"]
        return web.json_response({"agent": agent, "memory": self.agent_data.get_memory(agent)})

    async def handle_api_memory_save(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        agent = request.match_info["agent"]
        data = body.get("memory", {})
        try:
            self.agent_data.save_memory(agent, data)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True})

    async def handle_api_terminal_sessions(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({"sessions": pty_registry.list()})

    async def handle_api_terminal_session_usage(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        session_id = request.match_info["session_id"]
        session = pty_registry.get(session_id)
        if not session:
            return web.json_response({"error": "session not found"}, status=404)
        usage = session.usage.snapshot()
        usage.update({
            "session_id": session.session_id,
            "session_type": session.session_type,
            "target": session.target,
            "alive": session.alive,
        })
        return web.json_response(usage)

    async def handle_api_terminal_session_usage_refresh(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        session_id = request.match_info["session_id"]
        session = pty_registry.get(session_id)
        if not session:
            return web.json_response({"error": "session not found"}, status=404)
        if session.session_type != "agent" or "claude" not in session.agent_name.lower():
            return web.json_response(
                {"error": "usage refresh is only available for Claude terminals"},
                status=400,
            )
        if not session.alive:
            return web.json_response({"error": "session is not alive"}, status=409)
        await session.inject_control_input("/usage\r")
        return web.json_response({"ok": True, "session_id": session.session_id})

    async def handle_api_profiles(self, request: web.Request) -> web.Response:
        """GET /api/profiles — return permission profile definitions. Localhost-only."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        from permission_profiles import profile_summary
        return web.json_response({"profiles": profile_summary()})

    # ---- SSH host preset API ----

    async def handle_api_ssh_hosts(self, request: web.Request) -> web.Response:
        """GET /api/ssh-hosts — list saved SSH presets. Localhost-only."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        store = get_ssh_store()
        return web.json_response({"hosts": [h.to_dict() for h in store.list()]})

    async def handle_api_ssh_hosts_save(self, request: web.Request) -> web.Response:
        """POST /api/ssh-hosts — save a new or updated SSH preset.

        Body: {node_name, host, user, port?, key_path?, machine_id?}
        Runs connectivity test before saving. Returns {ok, message}.
        """
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        node_name = (body.get("node_name") or "").strip()
        host = (body.get("host") or "").strip()
        user = (body.get("user") or "").strip()
        if not node_name or not host or not user:
            return web.json_response(
                {"error": "node_name, host, and user are required"}, status=400)

        port = int(body.get("port") or 22)
        key_path = (body.get("key_path") or "").strip()
        machine_id = (body.get("machine_id") or "").strip()

        ok, msg = await asyncio.get_event_loop().run_in_executor(
            None, lambda: test_ssh_connectivity(host, user, port, key_path))
        if not ok:
            return web.json_response({"ok": False, "message": f"connectivity test failed: {msg}"})

        store = get_ssh_store()
        import time as _time
        ssh_host = SSHHost(
            node_name=node_name,
            host=host,
            user=user,
            port=port,
            key_path=key_path,
            machine_id=machine_id,
            last_ok=_time.time(),
        )
        store.save(ssh_host)

        # Remove from pending list now that it's been saved
        _pending_ssh_presets[:] = [
            p for p in _pending_ssh_presets
            if p.get("node_name") != node_name and p.get("new_node_name") != node_name
        ]
        return web.json_response({"ok": True, "message": msg})

    async def handle_api_ssh_host_delete(self, request: web.Request) -> web.Response:
        """DELETE /api/ssh-hosts/{node} — remove an SSH preset. Localhost-only."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        node = request.match_info["node"]
        store = get_ssh_store()
        deleted = store.delete(node)
        return web.json_response({"ok": deleted})

    async def handle_api_ssh_host_test(self, request: web.Request) -> web.Response:
        """POST /api/ssh-hosts/{node}/test — re-test connectivity for a saved preset."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        node = request.match_info["node"]
        store = get_ssh_store()
        host = store.get(node)
        if not host:
            return web.json_response({"error": "preset not found"}, status=404)
        ok, msg = await asyncio.get_event_loop().run_in_executor(
            None, lambda: test_ssh_connectivity(
                host.host, host.user, host.port, host.key_path))
        if ok:
            store.update_last_ok(node)
        return web.json_response({"ok": ok, "message": msg})

    async def handle_api_ssh_host_rename(self, request: web.Request) -> web.Response:
        """POST /api/ssh-hosts/{node}/rename — apply a drift-detected rename."""
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        node = request.match_info["node"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        new_name = (body.get("new_node_name") or "").strip()
        if not new_name:
            return web.json_response({"error": "new_node_name required"}, status=400)
        store = get_ssh_store()
        ok = store.rename_node(node, new_name)
        if ok:
            _pending_ssh_presets[:] = [
                p for p in _pending_ssh_presets
                if not (p.get("type") == "rename" and p.get("old_node_name") == node)
            ]
        return web.json_response({"ok": ok})

    async def handle_api_ssh_pending(self, request: web.Request) -> web.Response:
        """GET /api/ssh-hosts/pending-presets — pending save/rename notifications.

        Clears on read so the GUI only sees each notification once.
        Localhost-only; no auth needed.
        """
        if not self._localhost(request):
            return web.json_response({"error": "localhost only"}, status=403)
        items = list(_pending_ssh_presets)
        _pending_ssh_presets.clear()
        return web.json_response({"pending": items})

    async def handle_api_skills(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        from relay_client import ROOT, SKILL_TARGETS, list_skills

        target = request.rel_url.query.get("target", "Claude Code")
        if target not in SKILL_TARGETS:
            return web.json_response({"error": f"unknown target: {target}"}, status=400)
        return web.json_response({
            "target": target,
            "targets": list(SKILL_TARGETS.keys()),
            "skills": list_skills(ROOT, target),
        })

    async def handle_api_skills_install(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        from relay_client import ROOT, SKILL_TARGETS, install_skill

        name = (body.get("name") or "").strip()
        target = body.get("target", "Claude Code")
        if target not in SKILL_TARGETS:
            return web.json_response({"error": f"unknown target: {target}"}, status=400)
        msg = install_skill(name, ROOT, target)
        ok = not msg.startswith("Unknown")
        return web.json_response({"ok": ok, "message": msg})

    async def handle_api_skills_remove(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        from relay_client import SKILL_TARGETS, remove_skill

        name = (body.get("name") or "").strip()
        target = body.get("target", "Claude Code")
        if target not in SKILL_TARGETS:
            return web.json_response({"error": f"unknown target: {target}"}, status=400)
        msg = remove_skill(name, target)
        return web.json_response({"ok": True, "message": msg})

    async def handle_api_skills_install_all(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        from relay_client import ROOT, SKILL_TARGETS, install_all_skills

        target = body.get("target", "Claude Code")
        if target not in SKILL_TARGETS:
            return web.json_response({"error": f"unknown target: {target}"}, status=400)
        results = install_all_skills(ROOT, target)
        return web.json_response({"ok": True, "messages": results})

    async def handle_api_skills_remove_all(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        from relay_client import ROOT, SKILL_TARGETS, remove_all_skills

        target = body.get("target", "Claude Code")
        if target not in SKILL_TARGETS:
            return web.json_response({"error": f"unknown target: {target}"}, status=400)
        results = remove_all_skills(ROOT, target)
        return web.json_response({"ok": True, "messages": results})

    # ------------------------------------------------------------------ #
    # Ideas API                                                            #
    # ------------------------------------------------------------------ #

    async def handle_api_ideas_list(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({"ideas": self.idea_store.list_all()})

    async def handle_api_ideas_create(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        title = str(body.get("title", "")).strip()
        if not title:
            return web.json_response({"error": "title required"}, status=400)
        idea = self.idea_store.create(
            title=title,
            description=str(body.get("description", "")),
            priority=str(body.get("priority", "medium")),
        )
        return web.json_response({"idea": idea}, status=201)

    async def handle_api_idea_update(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        idea = self.idea_store.update(idea_id, **body)
        if idea is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"idea": idea})

    async def handle_api_idea_delete(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        if not self.idea_store.delete(idea_id):
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"ok": True})

    async def _idea_or_404(self, idea_id: str) -> tuple[dict | None, web.Response | None]:
        idea = self.idea_store.get(idea_id)
        if idea is None:
            return None, web.json_response({"error": "not found"}, status=404)
        return idea, None

    async def _run_idea_agent_query(
        self, agent_name: str, prompt: str,
    ) -> tuple[str, dict[str, Any]]:
        """Run a one-shot agent query (background spawn) and return stdout."""
        resolved = self.cfg.resolve_adapter_name(agent_name, prefer_interactive=False)
        if not resolved or resolved not in self.cfg.adapters:
            return "", {"status": "error", "exit_code": 1, "stderr": f"unknown agent: {agent_name}"}
        adapter = self.cfg.adapters[resolved]
        talk_cfg = dataclasses.replace(self.cfg, use_tmux=False)
        result = await spawn_agent(talk_cfg, adapter, prompt)
        content = (result.get("stdout") or "").strip()
        if not content:
            content = (result.get("stderr") or "").strip()
        return content, result

    async def handle_api_idea_brainstorm(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        idea, err = await self._idea_or_404(idea_id)
        if err:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        message = str(body.get("message", "")).strip()
        agent = str(body.get("agent") or idea.get("brainstorm_agent") or self.cfg.default_agent or "").strip()
        if not message:
            return web.json_response({"error": "message required"}, status=400)
        if not agent:
            return web.json_response({"error": "agent required"}, status=400)
        from idea_workflow import brainstorm_prompt

        prompt = brainstorm_prompt(idea, message)
        content, result = await self._run_idea_agent_query(agent, prompt)
        if not content:
            return web.json_response({
                "ok": False,
                "error": "empty response from agent",
                "result": result,
            }, status=502)
        updated = self.idea_store.add_finding(
            idea_id,
            agent=agent,
            content=content,
            prompt=message,
            source="agent",
        )
        self.idea_store.update(idea_id, brainstorm_agent=agent, assigned_agent=agent)
        return web.json_response({
            "ok": result.get("exit_code", 1) == 0,
            "idea": updated,
            "finding": updated["findings"][-1] if updated else None,
            "reply": content,
        })

    async def handle_api_idea_add_finding(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        _, err = await self._idea_or_404(idea_id)
        if err:
            return err
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        content = str(body.get("content", "")).strip()
        if not content:
            return web.json_response({"error": "content required"}, status=400)
        agent = str(body.get("agent") or "user").strip()
        updated = self.idea_store.add_finding(
            idea_id, agent=agent, content=content, source="user",
        )
        return web.json_response({"idea": updated})

    async def handle_api_idea_delete_finding(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        finding_id = request.match_info["finding_id"]
        updated = self.idea_store.remove_finding(idea_id, finding_id)
        if updated is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"idea": updated})

    async def handle_api_idea_compile_concept(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        updated = self.idea_store.compile_concept(idea_id)
        if updated is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"idea": updated})

    async def handle_api_idea_publish_concept(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        updated = self.idea_store.publish_concept(idea_id)
        if updated is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"idea": updated})

    async def handle_api_idea_discuss(self, request: web.Request) -> web.Response:
        """Collect feedback from active agent terminals (or spawn if needed)."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        idea, err = await self._idea_or_404(idea_id)
        if err:
            return err
        if not idea.get("concept_published_at"):
            return web.json_response(
                {"error": "publish the concept before opening discussion"}, status=400)
        try:
            body = await request.json()
        except Exception:
            body = {}
        agents = body.get("agents")
        if agents is None:
            agents = list_active_agent_names()
        if not agents:
            return web.json_response(
                {"error": "no active agents — open agent terminals first"}, status=400)
        from idea_workflow import concept_discussion_prompt

        prompt = concept_discussion_prompt(idea)
        wait = self.cfg.wait_before_send_seconds
        deliveries: list[dict[str, Any]] = []
        for agent_name in agents:
            resolved = self.cfg.resolve_adapter_name(
                agent_name, prefer_interactive=True, active_agents=agents)
            if not resolved:
                continue
            if await _deliver_prompt_to_pty(resolved, prompt, wait):
                deliveries.append({"agent": resolved, "delivered": True, "mode": "terminal"})
                self.idea_store.add_discussion(
                    idea_id,
                    agent=resolved,
                    content=f"[Concept shared in terminal — awaiting agent reply]",
                    source="system",
                )
            else:
                content, result = await self._run_idea_agent_query(resolved, prompt)
                if content:
                    self.idea_store.add_discussion(
                        idea_id, agent=resolved, content=content, source="agent",
                    )
                    deliveries.append({
                        "agent": resolved, "delivered": True,
                        "mode": "spawn", "exit_code": result.get("exit_code"),
                    })
        updated = self.idea_store.get(idea_id)
        return web.json_response({
            "ok": bool(deliveries),
            "idea": updated,
            "deliveries": deliveries,
        })

    async def handle_api_idea_forward_concept(self, request: web.Request) -> web.Response:
        """Forward compiled concept to active agents and optionally queue execution."""
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        idea_id = request.match_info["id"]
        idea, err = await self._idea_or_404(idea_id)
        if err:
            return err
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not (idea.get("concept") or "").strip():
            idea = self.idea_store.compile_concept(idea_id) or idea
        if not (idea.get("concept") or "").strip():
            return web.json_response({"error": "concept is empty"}, status=400)
        if not idea.get("concept_published_at"):
            self.idea_store.publish_concept(idea_id)
            idea = self.idea_store.get(idea_id) or idea

        agents = body.get("agents") or list_active_agent_names()
        if not agents:
            return web.json_response(
                {"error": "no active agents — open agent terminals first"}, status=400)
        queue = bool(body.get("queue_execution", False))
        from idea_workflow import concept_discussion_prompt, execution_prompt

        discuss_prompt = concept_discussion_prompt(
            idea,
            round_note=(
                "This concept is forwarded for team review before execution. "
                "Discuss trade-offs openly."
            ),
        )
        exec_prompt = execution_prompt(idea)
        wait = self.cfg.wait_before_send_seconds
        deliveries: list[dict[str, Any]] = []
        for agent_name in agents:
            resolved = self.cfg.resolve_adapter_name(
                agent_name, prefer_interactive=True, active_agents=agents)
            if not resolved:
                continue
            if await _deliver_prompt_to_pty(resolved, discuss_prompt, wait):
                deliveries.append({"agent": resolved, "kind": "concept", "mode": "terminal"})
                self.idea_store.add_discussion(
                    idea_id,
                    agent=resolved,
                    content="[Concept forwarded to terminal for review]",
                    source="system",
                )
            if exec_prompt and await _deliver_prompt_to_pty(
                    resolved, exec_prompt, wait):
                deliveries.append({"agent": resolved, "kind": "execute", "mode": "terminal"})
        if queue:
            assign = idea.get("assigned_agent") or idea.get("brainstorm_agent")
            self.idea_store.update(
                idea_id, status="queued",
                assigned_agent=assign or agents[0] if agents else None,
            )
        updated = self.idea_store.get(idea_id)
        return web.json_response({
            "ok": bool(deliveries) or queue,
            "idea": updated,
            "deliveries": deliveries,
            "queued": queue,
        })

    # ------------------------------------------------------------------ #
    # Bugs API                                                             #
    # ------------------------------------------------------------------ #

    async def handle_api_bugs_list(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({"bugs": self.bug_store.list_all()})

    async def handle_api_bugs_create(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        title = str(body.get("title", "")).strip()
        if not title:
            return web.json_response({"error": "title required"}, status=400)
        bug = self.bug_store.create(
            title=title,
            description=str(body.get("description", "")),
            severity=str(body.get("severity", "medium")),
            steps_to_reproduce=str(body.get("steps_to_reproduce", "")),
        )
        return web.json_response({"bug": bug}, status=201)

    async def handle_api_bug_update(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        bug_id = request.match_info["id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        bug = self.bug_store.update(bug_id, **body)
        if bug is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"bug": bug})

    async def handle_api_bug_delete(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        bug_id = request.match_info["id"]
        if not self.bug_store.delete(bug_id):
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"ok": True})

    # ------------------------------------------------------------------ #
    # Work queue (ideas + bugs auto-run when idle)                         #
    # ------------------------------------------------------------------ #

    async def handle_api_work_queue_tick(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        from work_queue_runner import try_dispatch_next

        result = await try_dispatch_next(self)
        return web.json_response(result)

    async def handle_api_work_queue_bind(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        session_id = str(body.get("session_id", "")).strip()
        kind = str(body.get("kind", "")).strip()
        item_id = str(body.get("id", "")).strip()
        if not session_id or kind not in ("idea", "bug") or not item_id:
            return web.json_response({"error": "session_id, kind, id required"}, status=400)
        from work_queue_runner import bind_work_session

        if not bind_work_session(self, session_id, kind, item_id):
            return web.json_response({"error": "session or work item not found"}, status=404)
        return web.json_response({"ok": True})

    def build_app(self) -> web.Application:
        app = web.Application(client_max_size=16 * 1024 * 1024)  # 16 MB — large agent prompts can exceed 1 MB
        app.router.add_get("/health", self.handle_health)
        app.router.add_get("/pending-deliveries", self.handle_pending_deliveries)
        app.router.add_get("/inbox", self.handle_inbox)
        app.router.add_post("/peer-announce", self.handle_peer_announce)
        app.router.add_get("/info", self.handle_info)
        app.router.add_get("/peers", self.handle_peers)
        app.router.add_post("/dispatch", self.handle_dispatch)
        app.router.add_get("/setup", self.handle_setup)
        app.router.add_post("/forward", self.handle_forward)
        app.router.add_post("/talk", self.handle_talk)
        app.router.add_post("/coordinate", self.handle_coordinate)
        app.router.add_get("/talk/threads", self.handle_talk_threads)
        app.router.add_get("/talk/threads/{thread_id}", self.handle_talk_thread)
        app.router.add_post("/pair/request", self.handle_pair_request)
        app.router.add_get("/pair/pending", self.handle_pair_pending)
        app.router.add_post("/pair/approve", self.handle_pair_approve)
        app.router.add_post("/pair/reject", self.handle_pair_reject)
        app.router.add_get("/pair/poll", self.handle_pair_poll)
        app.router.add_get("/terminal", self.handle_terminal)
        app.router.add_get("/", self.handle_gui_index)
        gui_dir = gui_directory()
        if gui_dir.is_dir():
            app.router.add_static("/gui/", gui_dir, name="gui_static")
        app.router.add_get("/api/status", self.handle_api_status)
        app.router.add_get("/api/pending", self.handle_api_pending)
        app.router.add_get("/api/agent-snippet", self.handle_api_agent_snippet)
        app.router.add_get("/api/inbox", self.handle_api_inbox)
        app.router.add_post("/api/approve", self.handle_api_approve)
        app.router.add_post("/api/connect", self.handle_api_connect)
        app.router.add_post("/api/settings", self.handle_api_settings)
        app.router.add_post("/api/send", self.handle_api_send)
        app.router.add_post("/api/broadcast", self.handle_api_broadcast)
        app.router.add_post("/api/coordinate", self.handle_coordinate)
        app.router.add_post("/api/relay/stop", self.handle_api_relay_stop)
        app.router.add_post("/api/update/pull", self.handle_api_update_pull)
        app.router.add_get("/api/terminal/sessions", self.handle_api_terminal_sessions)
        app.router.add_get(
            "/api/terminal/sessions/{session_id}/usage",
            self.handle_api_terminal_session_usage,
        )
        app.router.add_post(
            "/api/terminal/sessions/{session_id}/usage/refresh",
            self.handle_api_terminal_session_usage_refresh,
        )
        app.router.add_get("/api/profiles", self.handle_api_profiles)
        app.router.add_get("/api/skills", self.handle_api_skills)
        app.router.add_post("/api/skills/install", self.handle_api_skills_install)
        app.router.add_post("/api/skills/remove", self.handle_api_skills_remove)
        app.router.add_post("/api/skills/install-all", self.handle_api_skills_install_all)
        app.router.add_post("/api/skills/remove-all", self.handle_api_skills_remove_all)
        app.router.add_get("/api/tasks", self.handle_tasks_list)
        app.router.add_get("/api/tasks/events", self.handle_task_events)
        app.router.add_get("/api/tasks/{id}", self.handle_task_get)
        app.router.add_post("/api/tasks/{id}/status", self.handle_task_status)
        app.router.add_get("/api/sessions/{agent}", self.handle_api_sessions)
        app.router.add_get("/api/agents/{agent}/resume", self.handle_api_resume_get)
        app.router.add_post("/api/agents/{agent}/resume", self.handle_api_resume_save)
        app.router.add_get("/api/agents/{agent}/memory", self.handle_api_memory_get)
        app.router.add_post("/api/agents/{agent}/memory", self.handle_api_memory_save)
        app.router.add_get("/api/ssh-hosts", self.handle_api_ssh_hosts)
        app.router.add_post("/api/ssh-hosts", self.handle_api_ssh_hosts_save)
        app.router.add_get("/api/ssh-hosts/pending-presets", self.handle_api_ssh_pending)
        app.router.add_delete("/api/ssh-hosts/{node}", self.handle_api_ssh_host_delete)
        app.router.add_post("/api/ssh-hosts/{node}/test", self.handle_api_ssh_host_test)
        app.router.add_post("/api/ssh-hosts/{node}/rename", self.handle_api_ssh_host_rename)
        app.router.add_get("/api/ideas", self.handle_api_ideas_list)
        app.router.add_post("/api/ideas", self.handle_api_ideas_create)
        app.router.add_patch("/api/ideas/{id}", self.handle_api_idea_update)
        app.router.add_delete("/api/ideas/{id}", self.handle_api_idea_delete)
        app.router.add_post("/api/ideas/{id}/brainstorm", self.handle_api_idea_brainstorm)
        app.router.add_post("/api/ideas/{id}/findings", self.handle_api_idea_add_finding)
        app.router.add_delete(
            "/api/ideas/{id}/findings/{finding_id}", self.handle_api_idea_delete_finding)
        app.router.add_post(
            "/api/ideas/{id}/compile-concept", self.handle_api_idea_compile_concept)
        app.router.add_post(
            "/api/ideas/{id}/publish-concept", self.handle_api_idea_publish_concept)
        app.router.add_post("/api/ideas/{id}/discuss", self.handle_api_idea_discuss)
        app.router.add_post(
            "/api/ideas/{id}/forward-concept", self.handle_api_idea_forward_concept)
        app.router.add_get("/api/bugs", self.handle_api_bugs_list)
        app.router.add_post("/api/bugs", self.handle_api_bugs_create)
        app.router.add_patch("/api/bugs/{id}", self.handle_api_bug_update)
        app.router.add_delete("/api/bugs/{id}", self.handle_api_bug_delete)
        app.router.add_post("/api/work-queue/tick", self.handle_api_work_queue_tick)
        app.router.add_post("/api/work-queue/bind", self.handle_api_work_queue_bind)
        return app


# ============================================================
# Init / entry point
# ============================================================

DEFAULT_CONFIG_YAML = """\
# agentrelay configuration

# Display name for this machine on the agent mesh.
node_name: __NODE__

# Port for the local HTTP listener.
port: 9876

# Shared secret. MUST be identical on every machine that should
# trust each other. Copy this exact string to every other node.
token: __TOKEN__

use_tmux: false

approve_timeout: 300

relay:
  wait_before_send_seconds: 5

# Default action when no rule matches and no hint is given.
# One of: auto | agent | approve | reject
default_action: approve
default_agent: claude

# Adapters: how to invoke each local AI agent CLI in headless
# mode. The literal {prompt} is replaced with the request text.
# Adjust the command list to match your installed CLI version.
adapters:
  claude:
    command: ["claude", "-p", "{prompt}"]
    timeout: 1800
  codex:
    command: ["codex", "exec", "--skip-git-repo-check", "{prompt}"]
    timeout: 1800
  codex-visible:
    label: Codex (visible window)
    mode: interactive
    session: agentrelay-codex
    command: ["codex"]
    timeout: 1800
  gemini:
    command: ["gemini", "-p", "{prompt}"]
    timeout: 1800

# Policy rules, checked in order. First match wins.
# `pattern` is a Python regex matched against the command string.
rules:
  # Anything dangerous: always ask. Keep this before broader tool rules.
  - pattern: '\\b(sudo|rm\\s+-rf|/etc/|\\.ssh|systemctl|launchctl|shutdown|reboot)\\b'
    action: approve
    agent: claude

  # Safe read-only inspection: auto-execute.
  - pattern: '^(uname|hostname|whoami|pwd|ls|df|free|uptime|date|id)(\\s|$)'
    action: auto

  # Package installs and routine dev ops: hand to the local Claude.
  - pattern: '\\b(apt|brew|npm|pip|pipx|cargo|docker|git)\\b'
    action: agent
    agent: claude
"""


def write_default_config(path: Path) -> None:
    if path.exists():
        log.warning("config exists, not overwriting: %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    node = socket.gethostname().split(".")[0]
    token = secrets.token_urlsafe(32)
    content = (DEFAULT_CONFIG_YAML
               .replace("__NODE__", node)
               .replace("__TOKEN__", token))
    path.write_text(content)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"wrote config: {path}")
    print(f"node_name:   {node}")
    print(f"token:       {token}")
    print()
    print("Open AgentRelay on your other computers and tap Connect,")
    print("or copy the security code from Advanced settings.")


async def amain(cfg: Config, config_path: Path | None = None) -> None:
    relay = AgentRelay(cfg, config_path=config_path)
    await relay.register_mdns()
    await relay.start_udp_discovery()
    app = relay.build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", cfg.port)
    await site.start()
    log.info("listening on 0.0.0.0:%d as %s", cfg.port, cfg.node_name)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, stop.set)
        except NotImplementedError:
            pass  # Windows

    relay._udp_broadcast()  # initial broadcast so peers find us immediately
    heartbeat = asyncio.create_task(relay._heartbeat_loop(stop))
    try:
        await stop.wait()
    finally:
        heartbeat.cancel()
        await runner.cleanup()
        await relay.shutdown()


def main() -> None:
    p = argparse.ArgumentParser(prog="agentrelay")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--init", action="store_true",
                   help="write default config + fresh token, then exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.init:
        write_default_config(args.config)
        return

    if not args.config.exists():
        log.error("no config at %s. run: agentrelay --init", args.config)
        sys.exit(1)

    cfg = Config.load(args.config)
    if "CHANGE_ME" in cfg.token or len(cfg.token) < 16:
        log.error("weak or placeholder token in %s. edit it first.", args.config)
        sys.exit(1)

    pid_file = pid_file_path()
    if not acquire_pid_lock(pid_file):
        log.error("agentrelay already running; lock file: %s", pid_file)
        sys.exit(1)
    atexit.register(pid_file.unlink, missing_ok=True)

    try:
        asyncio.run(amain(cfg, config_path=args.config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
