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
- Saved SSH presets can open interactive SSH shell tabs through the same terminal WebSocket/PTY path
- Launch with AgentRelay instructions injected
- **Freedom level** on launch: Careful / Project helper / Full auto (`permission_profiles.py`)
- **Terminal usage bar MVP**: parser-backed per-session usage endpoint and compact UI strip
- YOLO-era checkbox replaced in web UI by freedom dropdown (CLI: `agent-send --profile`)

### Messaging and work routing

- Send to one agent (local or remote) with correct `/forward` vs `/dispatch` routing for interactive agents
- Freedom level can be selected when sending work, and the Activity row records that permission level
- **Message every agent** (global broadcast)
- **Inbox** for incoming work
- Delivery into open terminal tabs (queued while session starts)
- **Activity** tab: SQLite task queue, live updates (SSE), Open link to local or remote session

### Multi-agent and memory

- **Group task**: fan-out to several agents + optional summarizer (`/coordinate`, Group task tab)
- **Past chats**: persisted agent-to-agent threads (`talk.py`)
- **Agent notes**: per-agent resume (markdown) + remembered facts (JSON) (`agent_data.py`)

### SSH and remote computers

- SSH preset store (`ssh_hosts.py`), connectivity test on save
- **Home** screen: remote connections list, add computer, discovered-computer prompts
- `machine_id` in peer announce for rename/drift detection (rename API exists; full rename UI still light)

### Updates

- Settings has **Get latest files**, backed by `POST /api/update/pull`, which runs the project update/install flow and reports plain-English status.

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
| Settings | Timing, agent instructions, sync guide link, get latest files |

## Main files

| Path | Role |
|------|------|
| `agentrelay.py` | Daemon, routes, PTY WebSocket, task/SSH/resume/update/usage APIs |
| `task_queue.py` | SQLite task tracking (both machines) |
| `permission_profiles.py` | safe / project_write / full_auto |
| `ssh_hosts.py` | SSH preset JSON store |
| `terminal_usage.py` | PTY output parser and per-session usage estimates |
| `agent_data.py` | Agent resumes + memory files |
| `talk.py` | Conversation threads |
| `relay_client.py` | Launch, delivery, skills, peer send |
| `gui/app.js` | UI logic |
| `gui/terminals.js` | Terminal tabs + relay inject |

## Verification

```bash
python -m unittest discover -s tests -v
```

Key suites: GUI API (including forward resolve + resume/memory/usage/update), task queue, delivery, permission profiles, SSH, agent data.

## Still open (high level)

- Full **audit log** view; dedicated Permissions / Machines tabs (optional polish)
- Terminal usage full version: native agent usage sources, history, warnings, and pace comparison
- Launch agents directly into saved SSH terminal tabs
- PyInstaller bundles including all new modules + `gui/` assets

## Related docs

- [README](../README.md)
- [TASKS.md](TASKS.md)
- [task-queue.md](task-queue.md)
- [permission-profiles.md](permission-profiles.md)
- [feature-roadmap.md](feature-roadmap.md)
- [TERMINAL_PROTOCOL.md](../TERMINAL_PROTOCOL.md)
