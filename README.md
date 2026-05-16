# AgentRelay

Connect computers on your home network so your AI agents can work together.

**Example:** You're using Codex on a Windows PC for a Mac project. Instead of asking *you* to go install something on the Mac, Codex says *"I'll forward this to the Mac agent"* — the request shows up in Codex on the Mac, you can read and edit it, and it sends after a few seconds if you don't change anything.

## How it works

1. Install AgentRelay on each computer.
2. Open the app and pair with other computers on your LAN.
3. Install **Skills** into Codex, or slash commands into Claude/Gemini.
4. Use **Launch** to open an agent in an embedded terminal with instructions.
5. Agents use `agent-send` / `agent-forward` to route work between machines.

## Quick start — Desktop launcher

### macOS

```bash
cd /path/to/AgentRelay
./scripts/install-desktop-launcher.sh
```

Double-click **AgentRelay** on your Desktop. Only one GUI window opens at a time; a second click opens the existing UI in your browser.

### Windows

```powershell
cd C:\path\to\AgentRelay
.\install.ps1
.\scripts\install-desktop-launcher.ps1
```

Double-click **AgentRelay** on your Desktop.

## Install (Windows)

```cmd
cd /d e:\path\to\AgentRelay
install.ps1
```

Or use the desktop launcher above. The app is an **embedded web UI** (pywebview). Fallback: `agentrelay-gui --browser`. Legacy Tkinter: `agentrelay-gui --tk`.

**Important:** Use `cd /d` when switching drives (e.g. from `C:` to `E:`).

## Install (Mac / Linux)

```bash
cd agentrelay
./install.sh
./scripts/install-desktop-launcher.sh   # optional Desktop icon
agentrelay-gui
```

**Linux:** `pip install pywebview[gtk]` (or `pywebview[qt]`).

## Using the app

| Feature | What it does |
|---------|----------------|
| **Home** | This computer, network peers, SSH connections |
| **Launch** | Start an agent in a live terminal with AgentRelay instructions |
| **Terminal only** | Blank terminal tab (no auto-start) |
| **Freedom level** | Careful / Project helper / Full auto when launching |
| **Extra commands** | Install `/relay-send`, Codex skills, etc. |
| **Live terminals** | Multiple tabs; click **×** to close |
| **Inbox** | Messages from other computers |
| **Activity** | Running jobs — status, time, **Open** terminal |
| **Agent notes** | Bio + remembered facts per agent |
| **Group task** | One job to several agents |

### Permission profiles

Three tiers control agent autonomy, selectable per launch or via `--profile` on `agent-send`:

| Profile | What it allows |
|---------|----------------|
| `safe` | Read-only; confirmations required (default) |
| `project_write` | Edit current project; approvals for risky actions |
| `full_auto` | No confirmation prompts (previously "YOLO mode") |

In the app, pick **Full auto** only on trusted projects. In the terminal: `agent-send --profile full_auto …`

Details: [docs/permission-profiles.md](docs/permission-profiles.md)

### Task queue

Every routed job creates records on both computers. Watch progress in **Activity** — use **Open** to jump to the agent’s terminal on this machine.

Full details: [docs/task-queue.md](docs/task-queue.md)

**Keeping Mac and Windows in sync:** [docs/feature-roadmap.md — GitHub section](docs/feature-roadmap.md#github--keeping-every-machine-on-the-same-version) (plain language, no git jargon).

## Daily use (CLI)

| What | Command |
|------|---------|
| Open app | Desktop icon or `agentrelay-gui` |
| Run daemon only | `agentrelay --config config.yaml` |
| Forward a request | `agent-forward mac "install the build tools"` |
| Send to a specific agent | `agent-send codex@mac "fix the failing build"` |
| Send locally | `agent-send claude@local "review this repo"` |
| Multi-agent local | `agent-send --local --agents claude,codex "compare approaches"` |
| Send with permission profile | `agent-send --profile project_write claude@WINPC "refactor auth"` |
| List tasks | `GET http://localhost:9876/api/tasks` |

## Architecture

- **Daemon** (`agentrelay.py`) — HTTP/WebSocket on port 9876, mDNS peers, PTY sessions
- **GUI shell** (`agentrelay_gui.py` → `agentrelay_web.py`) — pywebview loading local `gui/`
- **Single instance** — daemon PID lock (`/tmp/agentrelay.pid`); GUI lock (`/tmp/agentrelay-gui.pid`)

For a concise record of completed work, important files, verification steps,
and remaining follow-up, see [docs/implementation-summary.md](docs/implementation-summary.md).

## Project layout

```
agentrelay.py          background service (HTTP/WS, PTY sessions, task dispatch)
agentrelay_gui.py      desktop entry (web UI default)
agentrelay_web.py      pywebview shell
relay_client.py        start/stop relay, skills, launch helpers
task_queue.py          SQLite task queue (both-sides tracking, lifecycle enforcement)
permission_profiles.py  safe/project_write/full_auto with per-agent CLI flag translation
gui/                   web UI (HTML/JS + xterm.js terminals + Tasks panel)
docs/                  task-queue.md, permission-profiles.md, roadmap, YOLO flags reference
scripts/               desktop launchers, build scripts
```

## Testing two-way communication (Mac ↔ Windows)

1. **Both machines:** get the latest AgentRelay files from GitHub, run install, restart the app. Plain-language steps: [docs/feature-roadmap.md — GitHub section](docs/feature-roadmap.md#github--keeping-every-machine-on-the-same-version).
2. **Mac:** `./scripts/install-desktop-launcher.sh`, open Desktop app.
3. **Windows:** `.\install.ps1`, `.\scripts\install-desktop-launcher.ps1`, open Desktop app.
3. On both: ensure the same `token` in `config.yaml` (or pair via **Connect**).
4. Install skills on each machine.
5. From Windows Codex: `agent-send claude@<mac-node> "hello from WINPC"`.
6. Check **Messages** on Mac and Mac agent inbox.

## Security

Only connect computers you trust (same home network). Anyone with your connection token can send requests as you. **YOLO mode** disables permission prompts — never use it on untrusted repos or with production credentials in scope.
