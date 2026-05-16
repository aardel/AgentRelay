# AgentRelay Implementation Summary

Concise record of what is built, how it fits together, and what is still open.
For a feature-by-feature status table, see [feature-roadmap.md — Implementation status](feature-roadmap.md#implementation-status-may-2026).

## What is built

AgentRelay is a cross-platform desktop app plus background service for routing work between AI agents on trusted computers on your network.

### Core platform

- HTTP/WebSocket daemon with token auth (`agentrelay.py`)
- LAN discovery (mDNS) and pairing
- Local web UI in pywebview (`agentrelay_web.py`, `gui/`)
- Legacy Tkinter UI (`agentrelay-gui --tk`)
- Single-instance locks for daemon and GUI

### Agents and terminals

- Configurable adapters (Claude, Codex, Gemini, Cursor, custom)
- Embedded **live terminals** (xterm.js + PTY; Windows via pywinpty)
- Launch with AgentRelay instructions injected
- **Freedom level** on launch: Careful / Project helper / Full auto (`permission_profiles.py`)
- YOLO-era checkbox replaced in web UI by freedom dropdown (CLI: `agent-send --profile`)

### Messaging and work routing

- Send to one agent (local or remote) with correct `/forward` vs `/dispatch` routing for interactive agents
- **Message every agent** (global broadcast)
- **Inbox** for incoming work
- Delivery into open terminal tabs (queued while session starts)
- **Activity** tab: SQLite task queue, live updates (SSE), Open link to session

### Multi-agent and memory

- **Group task**: fan-out to several agents + optional summarizer (`/coordinate`, Group task tab)
- **Past chats**: persisted agent-to-agent threads (`talk.py`)
- **Agent notes**: per-agent resume (markdown) + remembered facts (JSON) on `codex/agent-resumes-memory` branch (`agent_data.py`)

### SSH and remote computers

- SSH preset store (`ssh_hosts.py`), connectivity test on save
- **Home** screen: remote connections list, add computer, discovered-computer prompts
- `machine_id` in peer announce for rename/drift detection (rename API exists; full rename UI still light)

### Skills

- Install/remove relay slash commands and Codex skills (**Extra commands** tab)

## Web UI map (user-facing names)

| Tab | Purpose |
|-----|---------|
| Home | This computer, network peers, SSH connections, pairing |
| Agents | Launch agents, message one agent, message every agent |
| Agent notes | Resumes and persistent memory per agent |
| Group task | One job, many agents |
| Live terminals | Watch and type in agent sessions |
| Inbox | Messages from other computers |
| Past chats | History between agents |
| Activity | Running and finished tasks |
| Extra commands | Install helper commands into AI apps |
| Settings | Timing, agent instructions, sync guide link |

## Main files

| Path | Role |
|------|------|
| `agentrelay.py` | Daemon, routes, PTY WebSocket, task/SSH/resume APIs |
| `task_queue.py` | SQLite task tracking (both machines) |
| `permission_profiles.py` | safe / project_write / full_auto |
| `ssh_hosts.py` | SSH preset JSON store |
| `agent_data.py` | Agent resumes + memory files |
| `talk.py` | Conversation threads |
| `relay_client.py` | Launch, delivery, skills, peer send |
| `gui/app.js` | UI logic |
| `gui/terminals.js` | Terminal tabs + relay inject |

## Verification

```bash
python -m unittest discover -s tests -v
```

Key suites: GUI API (including forward resolve + resume/memory), task queue, delivery, permission profiles, SSH, agent data.

## Still open (high level)

- Remote **Open** from Activity on another computer’s terminal (today: local attach only)
- SSH **shell tabs** (presets exist; no remote terminal UI yet)
- In-app **get latest files** without git vocabulary
- Full **audit log** view; dedicated Permissions / Machines tabs (optional polish)
- Merge **agent notes** branch to `main` and ship to all machines
- PyInstaller bundles including all new modules + `gui/` assets

## Related docs

- [README](../README.md)
- [TASKS.md](TASKS.md)
- [task-queue.md](task-queue.md)
- [permission-profiles.md](permission-profiles.md)
- [feature-roadmap.md](feature-roadmap.md)
- [TERMINAL_PROTOCOL.md](../TERMINAL_PROTOCOL.md)
