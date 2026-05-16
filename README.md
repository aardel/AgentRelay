# AgentRelay

Connect computers on your home network so your AI agents can work together.

**Example:** You're using Codex on a Windows PC for a Mac project. Instead of asking *you* to go install something on the Mac, Codex says *"I'll forward this to the Mac agent"* — the request shows up in Codex on the Mac, you can read and edit it, and it sends after a few seconds if you don't change anything.

## How it works

1. Install AgentRelay on each computer.
2. Open the app → **Start** → see **Nearby computers**.
3. Tap **Connect** once per computer (approve on the other side if asked).
4. Copy the **agent instructions** into Codex, Cursor, or Claude.
5. Agents use `agent-forward` to send work to each other.

## Install (Windows)

```cmd
cd /d e:\path\to\AgentRelay
install.ps1
```

Then open the **desktop app** (not a browser):

```cmd
cd /d e:\path\to\AgentRelay
agentrelay-gui.cmd
```

**Important:** Use `cd /d` when switching drives (e.g. from `C:` to `E:`).

In the app, use **Launch** next to an agent — it opens a terminal, shows the AgentRelay instructions, copies them to your clipboard, and pastes them into the terminal automatically.

## Install (Mac / Linux)

```bash
cd agentrelay
./install.sh
agentrelay-gui
```

### Mac native app (pick one)

**Easy — double-click launcher** (after `install.sh`):

```bash
chmod +x AgentRelay.command
```

Then double-click **AgentRelay.command** in Finder.

**Full Mac app** (`.app` in Applications):

```bash
chmod +x scripts/build_mac_app.sh
./scripts/build_mac_app.sh
open dist/AgentRelay.app
```

### Windows native app bundle

```powershell
.\scripts\build_win_app.ps1
.\dist\AgentRelay\AgentRelay.exe
```

## Daily use

| What | Command |
|------|---------|
| Open setup app | `agentrelay-gui` |
| Forward a request | `agent-forward mac "install the build tools"` |
| Send to a specific agent | `agent-send codex@mac "fix the failing build"` |
| Send to an agent on this PC | `agent-send claude@local "review this repo"` |
| Ask several local agents | `agent-send --local --agents claude,codex "compare approaches"` |
| List nearby | shown in the app (refreshes automatically) |

## Visible agent window (Mac)

For requests to appear in Codex's input line on the Mac:

1. Open Codex in a terminal on the Mac (keep that window open).
2. The app uses a named session called `agentrelay-codex` by default — start Codex in a terminal session with that name, or adjust `codex-visible` in settings.

The forwarded text appears in the input line. You can edit it. After **5 seconds** (configurable in the app), it sends automatically.

## Files

```
agentrelay.py       background service (finds other computers)
agentrelay_gui.py   setup app (connect, settings, agent instructions)
agent-forward       forward a request to another computer
agent-talk          threaded agent messages (advanced)
agent-send          one-shot jobs (advanced)
talk.py / pairing.py / config_io.py
gui/                app screens
```

## Security

Only connect computers you trust (same home network). Anyone with your connection code can send requests as you.
