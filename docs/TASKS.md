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
- [x] Bidirectional relay verified (Mac ↔ WINPC, both directions)
- [x] **Task queue** — SQLite `tasks.db`, full originator+receiver lifecycle, both sides track with shared `task_id`, status pushes back via `reply_to` POST ([docs/task-queue.md](task-queue.md))
- [x] **Tasks UI panel** — SSE-driven live status, color-coded badges, duration, `[attach]` link per session ([docs/task-queue.md](task-queue.md))
- [x] **Permission profiles** — `safe` / `project_write` / `full_auto` with per-agent CLI flag translation, backward-compat `yolo=True` path ([docs/permission-profiles.md](permission-profiles.md))
- [x] `agent-send --profile` flag
- [x] `/api/tasks`, `/api/tasks/{id}`, `/api/tasks/{id}/status`, `/api/profiles` endpoints

## In Progress / Next

- [ ] SSH preset flow: peer announce → GUI notification → pre-fill host → SSH user+key → connectivity test → write `ssh_hosts.json`
  - Join key: `node_name` (primary) + `machine_id` fingerprint (drift detector)
  - `machine_id` sources: Linux `/etc/machine-id`, Mac `ioreg IOPlatformUUID`, Windows `wmic csproduct get UUID`
  - Include `machine_id` in peer announce payload
  - Reconnect deduplication: check existing preset before firing notification
- [ ] Project launch presets (name, target_node, agent, profile, message_template)
- [ ] Remote agent detection over SSH

## Backlog

- [ ] Retire Tkinter UI (`--tk`) when web UI has full parity
- [ ] `project_write` flag coverage for claude (use `--allowedTools` allowlist)
- [ ] tmux integration (add as optional layer when building SSH remote attach, not before)
- [ ] Centralized vs distributed orchestration (revisit after real multi-machine workflows)
- [ ] PyInstaller bundles include all new modules + `gui/` assets
- [ ] `install.ps1`: copy `config.yaml` template into install dir for Windows
