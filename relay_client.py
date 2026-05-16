"""Shared helpers for the desktop app and background service."""

from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import aiohttp

from agentrelay import DEFAULT_CONFIG, Config
from config_io import load_raw, save_raw, update_settings

INTERACTIVE_MODES = frozenset({"interactive", "interactive_tmux"})

# ── Skills management ────────────────────────────────────────────────────────

SKILL_TARGETS: dict[str, Path] = {
    "Claude Code": Path.home() / ".claude"  / "commands",
    "Gemini":      Path.home() / ".gemini"  / "commands",
    "Codex":       Path.home() / ".codex"   / "commands",
}

def claude_commands_dir() -> Path:
    return SKILL_TARGETS["Claude Code"]


def _skill_definitions(relay_root: Path) -> dict[str, tuple[str, str]]:
    """Return {skill_name: (label, markdown_content)} generated for this machine."""
    if sys.platform == "win32":
        python = str(relay_root / ".venv" / "Scripts" / "python.exe")
    else:
        python = str(relay_root / ".venv" / "bin" / "python")
    cfg = str(relay_root / "config.yaml")
    send = str(relay_root / "agent-send")

    def _agent_skill(agent_key: str, label: str) -> str:
        interactive = f"{agent_key}-interactive"
        return f"""\
Send a message to the {label} agent via AgentRelay.

The message to send is: $ARGUMENTS

## Steps

1. Run: `{python} "{send}" --config "{cfg}" --list`
   Find a node with `{interactive}` in its agents. This machine is marked `*`
   and can be addressed as `local`.
   - Multiple nodes with {label}? Ask: "Which computer? [list]"
   - No node has `{interactive}`? Fall back to `{agent_key}` (headless).

2. Send: `{python} "{send}" --config "{cfg}" {interactive}@<node> "<message>"`
   Use `{interactive}@local` for this computer.

3. Report what was sent, to which node, and whether it succeeded.
"""

    def _generic_skill() -> str:
        return f"""\
Send a message to any local or connected agent via AgentRelay.

The message to send is: $ARGUMENTS

## Steps

1. Run: `{python} "{send}" --config "{cfg}" --list`
   Note available nodes and agents. This machine is marked `*` and can be
   addressed as `local`.

2. Determine target node and agent from $ARGUMENTS (e.g. "fix bug --to WINPC --agent codex").
   Otherwise:
   - One peer → use it.
   - Multiple peers → ask: "Which computer? [list]"
   - Multiple agents on chosen peer → ask: "Which agent? [list]"
   - Prefer `*-interactive` adapters for visible delivery.

3. Send: `{python} "{send}" --config "{cfg}" <agent>@<node> "<message>"`
   Use `<agent>@local` for this computer.

4. Report result.
"""

    def _peers_skill() -> str:
        return f"""\
List all connected computers and their available agents via AgentRelay.

Run: `{python} "{send}" --config "{cfg}" --list`

Show results clearly: mark this machine with `*`, list agents on each node,
and suggest `agent@node` commands such as `codex@local` or `claude@MAC`.
"""

    return {
        "relay-peers":  ("Peers — list connected computers",   _peers_skill()),
        "relay-send":   ("Send — any agent (asks if ambiguous)", _generic_skill()),
        "relay-claude": ("Send to Claude",   _agent_skill("claude",  "Claude")),
        "relay-codex":  ("Send to Codex",    _agent_skill("codex",   "Codex")),
        "relay-gemini": ("Send to Gemini",   _agent_skill("gemini",  "Gemini")),
        "relay-cursor": ("Send to Cursor",   _agent_skill("cursor",  "Cursor")),
    }


def skill_names(relay_root: Path) -> list[tuple[str, str]]:
    """Return [(name, label), ...] for all defined skills."""
    return [(n, lbl) for n, (lbl, _) in _skill_definitions(relay_root).items()]


def is_skill_installed(name: str, target: str) -> bool:
    commands_dir = SKILL_TARGETS.get(target)
    return bool(commands_dir and (commands_dir / f"{name}.md").exists())


def list_skills(relay_root: Path, target: str = "Claude Code") -> list[dict[str, Any]]:
    definitions = _skill_definitions(relay_root)
    return [{"name": n, "label": lbl,
             "installed": is_skill_installed(n, target)}
            for n, (lbl, _) in definitions.items()]


def install_skill(name: str, relay_root: Path, target: str = "Claude Code") -> str:
    commands_dir = SKILL_TARGETS.get(target)
    if not commands_dir:
        return f"Unknown target: {target}"
    commands_dir.mkdir(parents=True, exist_ok=True)
    definitions = _skill_definitions(relay_root)
    if name not in definitions:
        return f"Unknown skill: {name}"
    _, content = definitions[name]
    (commands_dir / f"{name}.md").write_text(content, encoding="utf-8")
    return f"Installed /{name} for {target}"


def remove_skill(name: str, target: str = "Claude Code") -> str:
    commands_dir = SKILL_TARGETS.get(target)
    if not commands_dir:
        return f"Unknown target: {target}"
    path = commands_dir / f"{name}.md"
    if path.exists():
        path.unlink()
        return f"Removed /{name} from {target}"
    return f"/{name} was not installed for {target}"


def install_all_skills(relay_root: Path, target: str = "Claude Code") -> list[str]:
    return [install_skill(n, relay_root, target) for n in _skill_definitions(relay_root)]


def remove_all_skills(relay_root: Path, target: str = "Claude Code") -> list[str]:
    return [remove_skill(n, target) for n in _skill_definitions(relay_root)]

def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(__file__).resolve().parent


ROOT = _project_root()
_daemon_proc: subprocess.Popen | None = None


def agent_launch_script_name(adapter_name: str) -> str:
    return f"agentrelay-launch-{adapter_name}.cmd"


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _health(port: int) -> bool:
    try:
        t = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=t) as s:
            async with s.get(f"http://127.0.0.1:{port}/health") as r:
                return r.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False


async def _api(port: int, token: str, method: str, path: str,
               body: dict | None = None) -> tuple[int, Any]:
    headers = {"X-Agent-Token": token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.request(
            method, f"http://127.0.0.1:{port}{path}",
            headers=headers, json=body,
        ) as r:
            try:
                data = await r.json()
            except Exception:
                data = {"error": await r.text()}
            return r.status, data


def relay_running(cfg: Config) -> bool:
    return _run(_health(cfg.port))


def start_relay(config_path: Path) -> bool:
    global _daemon_proc
    cfg = Config.load(config_path)
    if _run(_health(cfg.port)):
        return True
    flags = 0
    if sys.platform == "win32":
        flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--relay-daemon", "--config", str(config_path)]
    else:
        cmd = [sys.executable, str(ROOT / "agentrelay.py"), "--config", str(config_path)]
    _daemon_proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT) if not getattr(sys, "frozen", False) else None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    for _ in range(40):
        time.sleep(0.25)
        if _run(_health(cfg.port)):
            return True
    return False


def stop_relay(cfg: Config) -> None:
    global _daemon_proc
    if _daemon_proc and _daemon_proc.poll() is None:
        _daemon_proc.terminate()
        _daemon_proc = None
        return
    import os
    import signal
    pid_file = Path("/tmp/agentrelay.pid")
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass


def fetch_setup(cfg: Config, config_path: Path) -> dict[str, Any]:
    if not _run(_health(cfg.port)):
        return {
            "relay_running": False,
            "node": cfg.node_name,
            "agents": cfg.agent_labels(),
            "nearby": [],
            "address": "",
        }
    _, setup = _run(_api(cfg.port, cfg.token, "GET", "/setup"))
    return {
        "relay_running": True,
        "node": setup.get("node", cfg.node_name),
        "address": setup.get("address", ""),
        "agents": setup.get("agents") or cfg.agent_labels(),
        "nearby": setup.get("nearby", []),
        "wait_before_send_seconds": cfg.wait_before_send_seconds,
        "trusted_peers": cfg.trusted_peers,
    }


def fetch_pending(cfg: Config) -> list[dict[str, Any]]:
    if not _run(_health(cfg.port)):
        return []
    _, body = _run(_api(cfg.port, cfg.token, "GET", "/pair/pending"))
    return body.get("pending") or []


async def _fetch_nearby_agents(cfg: Config) -> list[dict[str, Any]]:
    """Return [{name, address, port, agents:[...]}] for each reachable peer."""
    try:
        _, setup = await _api(cfg.port, cfg.token, "GET", "/setup")
        nearby = setup.get("nearby") or []
    except Exception:
        return []
    results = []
    for peer in nearby:
        addr, port = peer.get("address", ""), peer.get("port", 9876)
        agents_str = peer.get("agents", "")
        agent_names = [a.strip() for a in agents_str.split(",") if a.strip()]
        # Try to get richer adapter info from peer /info
        try:
            t = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=t) as s:
                async with s.get(
                    f"http://{addr}:{port}/info",
                    headers={"X-Agent-Token": cfg.token},
                ) as r:
                    if r.status == 200:
                        info = await r.json()
                        agent_names = list(info.get("adapters") or agent_names)
        except Exception:
            pass
        results.append({
            "name": peer["name"],
            "address": addr,
            "port": port,
            "agents": agent_names,
        })
    return results


def build_agent_snippet(cfg: Config, nearby: list[dict[str, Any]] | None = None) -> str:
    if nearby is None:
        try:
            nearby = _run(_fetch_nearby_agents(cfg))
        except Exception:
            nearby = []

    lines = [
        "# AgentRelay — you can delegate work to agents on other computers\n",
        f"This computer: {cfg.node_name}",
        "",
        "Agents on this computer:",
    ]

    local_agents = list(cfg.adapters)
    if not local_agents:
        lines.append("  (no agents configured)")
    for agent in local_agents:
        lines.append(f"  agent-send {agent}@local \"<task>\"")
        lines.append(f"  agent-send {agent}@{cfg.node_name} \"<task>\"")
    lines.append("")

    if not nearby:
        lines += [
            "No connected computers found.",
            "Use @local targets, or connect other computers in the AgentRelay app.",
        ]
    else:
        lines.append("Connected computers and their agents:")
        for peer in nearby:
            agents = peer["agents"]
            lines.append(f"\n  {peer['name']}:")
            if not agents:
                lines.append("    (no agents configured)")
            for agent in agents:
                lines.append(
                    f"    agent-send {agent}@{peer['name']} \"<task>\""
                )

        lines += [
            "",
            "Rules:",
            "- When delegating, say:",
            "  \"I'll send this to [agent] on [computer].\"",
            "- Use agent-send to dispatch. Never ask the user to do it manually.",
            "- If the user hasn't specified which agent or computer to use,",
            "  and more than one option is available, ASK before sending:",
            "  \"Should I send this to claude on Mac, or codex on WINPC?\"",
            "- For read-only shell commands (ls, df, uname, etc.) use --auto flag.",
        ]

    return "\n".join(lines) + "\n"


def _load_agent_send():
    path = ROOT / "agent-send"
    loader = importlib.machinery.SourceFileLoader("agent_send", str(path))
    spec = importlib.util.spec_from_loader("agent_send", loader)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def connect_peer(cfg: Config, config_path: Path, peer: str) -> tuple[bool, str]:
    agent_send = _load_agent_send()
    peers = _run(agent_send.discover(timeout=3.0))
    if peer not in peers:
        return False, "Computer not found on the network"
    addr, port = peers[peer]

    async def _do() -> tuple[bool, str]:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"http://{addr}:{port}/pair/request",
                json={"from_node": cfg.node_name},
            ) as r:
                start = await r.json()
        rid = start.get("request_id")
        if not rid:
            return False, "Could not start connection"
        for _ in range(120):
            await asyncio.sleep(0.5)
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"http://{addr}:{port}/pair/poll",
                    params={"from_node": cfg.node_name},
                ) as r:
                    poll = await r.json()
            if poll.get("status") == "connected":
                data = load_raw(config_path)
                data["token"] = poll["token"]
                trusted = list(set(data.get("trusted_peers") or []) | {peer})
                data["trusted_peers"] = trusted
                save_raw(data, config_path)
                return True, f"Connected to {peer}"
        return False, "Timed out — approve the request on the other computer"

    return _run(_do())


def approve_request(cfg: Config, config_path: Path,
                    request_id: str, peer_name: str) -> None:
    _run(_api(cfg.port, cfg.token, "POST", "/pair/approve",
              {"request_id": request_id}))
    data = load_raw(config_path)
    trusted = list(set(data.get("trusted_peers") or []) | {peer_name})
    data["trusted_peers"] = trusted
    save_raw(data, config_path)


def interactive_launch_argv(
    adapter_id: str,
    adapter,
    yolo: bool = False,
    profile: str | None = None,
) -> list[str]:
    """Argv for an interactive PTY session (no {prompt} placeholder).

    Pass *profile* ("safe" | "project_write" | "full_auto") for explicit
    control. *yolo=True* is kept for backward compatibility and maps to
    "full_auto".
    """
    from permission_profiles import apply_profile_flags, profile_for_yolo

    resolved = profile if profile else profile_for_yolo(yolo)

    parts = [p for p in (adapter.command or []) if p != "{prompt}"]
    if adapter.mode in ("interactive", "interactive_tmux"):
        argv = parts if parts else [adapter_id]
    elif not parts:
        argv = [adapter_id]
    else:
        cleaned: list[str] = []
        skip_next = False
        for p in parts:
            if skip_next:
                skip_next = False
                continue
            if p in ("-p", "--prompt"):
                skip_next = True
                continue
            if p == "exec":
                continue
            cleaned.append(p)
        argv = cleaned if cleaned else [adapter_id]
    return apply_profile_flags(argv, adapter_id, resolved)


def _interactive_launch_command(adapter_id: str, adapter) -> str:
    """Shell-style command string for external terminal launchers."""
    argv = interactive_launch_argv(adapter_id, adapter)
    return " ".join(argv)


def send_to_peer(cfg: Config, addr: str, port: int,
                 command: str, agent: str | None = None) -> tuple[bool, str]:
    """Dispatch a headless command to a remote peer's /dispatch endpoint."""
    import uuid as _uuid
    payload: dict = {
        "from": cfg.node_name,
        "command": command,
        "request_id": _uuid.uuid4().hex,
    }
    if agent:
        payload["agent"] = agent

    async def _post():
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"http://{addr}:{port}/dispatch",
                json=payload,
                headers={"X-Agent-Token": cfg.token},
            ) as resp:
                data = await resp.json()
                return resp.status, data

    try:
        status, data = _run(_post())
        if status == 200:
            detail = (data.get("stdout") or data.get("status") or "Sent").strip()
            return True, detail or "Sent"
        return False, data.get("error", data.get("stderr", f"HTTP {status}"))
    except Exception as e:
        return False, str(e)


async def _fetch_peer_adapter_mode(
    cfg: Config, addr: str, port: int, agent: str,
) -> str | None:
    """Return adapter mode from peer /info, or None if unavailable."""
    try:
        t = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=t) as session:
            async with session.get(
                f"http://{addr}:{port}/info",
                headers={"X-Agent-Token": cfg.token},
            ) as resp:
                if resp.status != 200:
                    return None
                info = await resp.json()
        spec = (info.get("adapters") or {}).get(agent) or {}
        return spec.get("mode")
    except Exception:
        return None


def _looks_interactive(agent: str, mode: str | None) -> bool:
    if mode in INTERACTIVE_MODES:
        return True
    return agent.endswith("-interactive") or agent.endswith("-visible")


def forward_to_peer(
    cfg: Config,
    addr: str,
    port: int,
    message: str,
    to_agent: str,
    from_agent: str | None = None,
    task_id: str | None = None,
    reply_to: str | None = None,
) -> tuple[bool, str]:
    """Deliver to a visible agent window on a remote peer via /forward."""
    payload = {
        "from_node": cfg.node_name,
        "from_agent": from_agent or cfg.default_agent or "agentrelay",
        "to_agent": to_agent,
        "message": message,
    }
    if task_id:
        payload["task_id"] = task_id
    if reply_to:
        payload["reply_to"] = reply_to

    async def _post():
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"http://{addr}:{port}/forward",
                json=payload,
                headers={"X-Agent-Token": cfg.token},
            ) as resp:
                data = await resp.json()
                return resp.status, data

    try:
        status, data = _run(_post())
        if status == 200 and data.get("ok"):
            detail = (data.get("stdout") or data.get("status") or "Forwarded").strip()
            return True, detail or "Forwarded to agent window"
        err = data.get("error") or data.get("stderr") or f"HTTP {status}"
        return False, str(err)
    except Exception as e:
        return False, str(e)


def deliver_to_peer(
    cfg: Config,
    addr: str,
    port: int,
    message: str,
    agent: str | None = None,
    task_id: str | None = None,
    reply_to: str | None = None,
) -> tuple[bool, str]:
    """
    Send to a remote peer using /forward for interactive agents, else /dispatch.
    Interactive delivery shows in the agent's terminal window on the remote machine.
    """
    if not agent:
        return send_to_peer(cfg, addr, port, message, agent)
    mode = _run(_fetch_peer_adapter_mode(cfg, addr, port, agent))
    if _looks_interactive(agent, mode):
        return forward_to_peer(cfg, addr, port, message, agent,
                               task_id=task_id, reply_to=reply_to)
    return send_to_peer(cfg, addr, port, message, agent)


def launch_agent(cfg: Config, agent_id: str) -> str:
    """Open the agent in a terminal and send it the AgentRelay instructions."""
    if agent_id not in cfg.adapters:
        return f"Unknown agent: {agent_id}"
    adapter = cfg.adapters[agent_id]

    # Fetch live peer+agent info so instructions are accurate
    try:
        nearby = _run(_fetch_nearby_agents(cfg))
    except Exception:
        nearby = []
    snippet = build_agent_snippet(cfg, nearby)

    inst = Path(tempfile.gettempdir()) / "agentrelay-instructions.txt"
    inst.write_text(snippet, encoding="utf-8")

    try:
        import pyperclip
        pyperclip.copy(snippet)
        copied = True
    except ImportError:
        copied = False

    label = adapter.label or agent_id
    main_cmd = _interactive_launch_command(agent_id, adapter)
    session = getattr(adapter, "session", None) or f"agentrelay-{agent_id}"

    if sys.platform == "win32":
        bat = Path(tempfile.gettempdir()) / agent_launch_script_name(agent_id)
        bat.write_text(
            f"@echo off\r\n"
            f"chcp 65001 >nul\r\n"
            f"title AgentRelay - {label}\r\n"
            f"echo  Starting {label}...\r\n\r\n"
            f"{main_cmd}\r\n",
            encoding="utf-8",
        )
        subprocess.Popen(
            ["cmd", "/c", "start", "", "cmd", "/k", str(bat)],
            cwd=str(ROOT), shell=False,
        )
        msg = f"Opened {label}."
        if copied:
            msg += " Instructions copied to clipboard — paste them into the agent to get started."

    elif sys.platform == "darwin":
        import shutil
        if shutil.which("tmux"):
            # Start agent in a named tmux session, then send the instructions
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session, main_cmd],
                check=False,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", session,
                 f"cat '{inst}'", "Enter"],
                check=False,
            )
            time.sleep(0.5)
            # Open a Terminal window attached to this session so user can see it
            attach_script = (
                f'tell application "Terminal" to do script '
                f'"tmux attach -t {session}"'
            )
            subprocess.Popen(["osascript", "-e", attach_script])
            msg = (
                f"Opened {label} in tmux session '{session}'. "
                f"Instructions sent automatically."
            )
        else:
            script = (
                f'tell application "Terminal" to do script '
                f'"cat \\"{inst}\\" && echo && {main_cmd}"'
            )
            subprocess.Popen(["osascript", "-e", script])
            msg = f"Opened {label}."
            if copied:
                msg += " Instructions copied to clipboard."
    else:
        subprocess.Popen(
            ["x-terminal-emulator", "-e",
             f"bash -c 'cat \"{inst}\" && echo && {main_cmd}'"],
        )
        msg = f"Opened {label}."
        if copied:
            msg += " Instructions copied to clipboard."

    return msg
