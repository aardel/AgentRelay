# AgentRelay — Task List

## Completed (May 2026)

- [x] Local web UI served by daemon (`gui/` + pywebview shell)
- [x] Embedded terminal tabs (xterm.js + `/terminal` WebSocket)
- [x] PTY-based **Launch** (replaces tmux/external Terminal for interactive agents)
- [x] Tab close button (×) on terminal tabs
- [x] Skills panel (install/remove slash commands)
- [x] **YOLO mode** checkbox + per-agent CLI flags ([ai-cli-agents-yolo-flags.md](ai-cli-agents-yolo-flags.md))
- [x] Single-instance GUI lock (`/tmp/agentrelay-gui.pid`)
- [x] Desktop launcher (macOS `AgentRelay.command`, Windows `AgentRelay.cmd`)
- [x] Updated `install.ps1` / `install.sh` / README for cross-platform install
- [x] Tests: GUI API, skills, yolo flags, launch argv

## Next (for Windows ↔ Mac testing)

- [ ] Pull latest on WINPC: `git pull`, `.\install.ps1`, `.\scripts\install-desktop-launcher.ps1`
- [ ] Confirm same `token` in `config.yaml` on both machines (or pair via UI)
- [ ] Launch agents on both sides; send `agent-send claude@MAC "ping"` from Windows
- [ ] Verify **Messages** inbox and interactive delivery on Mac
- [ ] Test YOLO Launch on each supported CLI (Claude, Codex, Gemini)

## Backlog

- [ ] Retire Tkinter UI (`--tk`) when web UI has full parity
- [ ] Remote read-only terminal attach from peer machines
- [ ] Permission profiles (Safe / Project Write / Full Auto) in UI
- [ ] `install.ps1`: copy `config.yaml` template into install dir for Windows
- [ ] PyInstaller bundles include all new modules + `gui/` assets
