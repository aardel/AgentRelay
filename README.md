# AgentRelay

Connect computers on your home network so your AI agents can work together.

**Example:** You're using Codex on a Windows PC for a Mac project. Instead of asking *you* to go install something on the Mac, Codex says *"I'll forward this to the Mac agent"* — the request shows up in Codex on the Mac, you can read and edit it, and it sends after a few seconds if you don't change anything.

## How it works

1. Install AgentRelay on each computer.
2. Open the app and pair with other computers on your LAN.
3. Install **Skills** (slash commands) into Claude, Codex, or Gemini.
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
| **Launch** | PTY terminal + start agent CLI + paste AgentRelay instructions |
| **Terminal only** | Blank terminal tab (no auto-start) |
| **YOLO mode** | Checkbox — adds skip-permissions flags (see below) |
| **Skills** | Install `/relay-send`, `/relay-codex`, etc. into your agent |
| **Terminals** | Multiple tabs; click **×** to close a tab |
| **Messages** | Incoming work from remote peers |

### YOLO / full-auto mode

Optional checkbox on **Agents** and **Terminals**. When enabled, Launch adds each CLI's skip-permissions flags (e.g. Claude `--dangerously-skip-permissions`, Codex `--dangerously-bypass-approvals-and-sandbox`). **Use only on trusted projects.**

Full reference: [docs/ai-cli-agents-yolo-flags.md](docs/ai-cli-agents-yolo-flags.md)

## Daily use (CLI)

| What | Command |
|------|---------|
| Open app | Desktop icon or `agentrelay-gui` |
| Run daemon only | `agentrelay --config config.yaml` |
| Forward a request | `agent-forward mac "install the build tools"` |
| Send to a specific agent | `agent-send codex@mac "fix the failing build"` |
| Send locally | `agent-send claude@local "review this repo"` |
| Multi-agent local | `agent-send --local --agents claude,codex "compare approaches"` |

## Architecture

- **Daemon** (`agentrelay.py`) — HTTP/WebSocket on port 9876, mDNS peers, PTY sessions
- **GUI shell** (`agentrelay_gui.py` → `agentrelay_web.py`) — pywebview loading local `gui/`
- **Single instance** — daemon PID lock (`/tmp/agentrelay.pid`); GUI lock (`/tmp/agentrelay-gui.pid`)

## Project layout

```
agentrelay.py          background service
agentrelay_gui.py      desktop entry (web UI default)
agentrelay_web.py      pywebview shell
relay_client.py        start/stop relay, skills, launch helpers
gui/                   web UI (HTML/JS + xterm.js terminals)
docs/                  roadmap, YOLO flags reference
scripts/               desktop launchers, build scripts
```

## Testing two-way communication (Mac ↔ Windows)

1. **Mac:** pull latest, `./scripts/install-desktop-launcher.sh`, open Desktop app.
2. **Windows:** `git pull`, `.\install.ps1`, `.\scripts\install-desktop-launcher.ps1`, open Desktop app.
3. On both: ensure the same `token` in `config.yaml` (or pair via **Connect**).
4. Install skills on each machine.
5. From Windows Codex: `agent-send claude@<mac-node> "hello from WINPC"`.
6. Check **Messages** on Mac and Mac agent inbox.

## Security

Only connect computers you trust (same home network). Anyone with your connection token can send requests as you. **YOLO mode** disables permission prompts — never use it on untrusted repos or with production credentials in scope.
