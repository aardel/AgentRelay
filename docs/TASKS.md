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
- [x] **Task wiring** — originator creates + updates task records in `agent-send`; receiver wiring in `handle_forward`, PTY `mark_running`, `_on_close` completion hook
- [x] **SSH host presets** — `ssh_hosts.py` with `SSHHostStore`, `get_machine_id()`, `test_ssh_connectivity()`
- [x] **Peer-to-preset flow** — `machine_id` in `/peer-announce`, `handle_peer_announce` drives pending-preset notifications
- [x] **SSH host API** — `GET/POST /api/ssh-hosts`, `DELETE /api/ssh-hosts/{node}`, `/test`, `/rename`, `/pending-presets`

## Active Backlog

### Phase 2 (SSH + remote agents)

- [ ] **SSH host GUI** — Machines/SSH view with preset list, add-host dialog (node_name, host, user, key_path), connectivity status
- [ ] "New peer — save as SSH target?" notification in GUI (polls `/api/ssh-hosts/pending-presets`)
- [ ] Rename prompt when `machine_id` drift detected
- [ ] Remote agent detection over SSH (`which claude`, `which codex`, etc.)
- [ ] Launch remote agents into SSH terminal tabs
- [ ] Trust levels for peers (read-only, trusted, full-auto)
- [ ] Project-specific launch presets

### Phase 2 (cleanup)

- [ ] Retire Tkinter UI (`--tk`) when web UI has full parity
- [ ] `project_write` flag coverage for claude (use `--allowedTools` allowlist)
- [ ] Remote read-only terminal attach from peer machines (WebSocket attach to `session_id`)
- [ ] tmux integration (add as optional layer when building SSH remote attach, not before)
- [ ] Centralized vs distributed orchestration (revisit after real multi-machine workflows)
- [ ] `install.ps1`: copy `config.yaml` template into install dir for Windows
- [ ] PyInstaller bundles include all new modules + `gui/` assets

### Phase 3

- [ ] Workflow builder
- [ ] Remote AgentRelay install/start over SSH
- [ ] File sync support
- [ ] Rich transcript viewer
- [ ] Policy file support (`.agentrelay-policy.yaml`)
- [ ] Full orchestration dashboard

## Testing Checklist (post-build)

- [ ] `python -m pytest tests/` green on both WINPC and Mac
- [ ] Task queue: send a task via `agent-send`, confirm originator + receiver records in `tasks.db`
- [ ] SSE: open Tasks panel in GUI, send a task, confirm status badge updates without refresh
- [ ] `[attach]` link: click on a running task's session ID, confirm terminal opens
- [ ] Permission profiles: `agent-send --profile full_auto target "msg"`, confirm flag in agent argv
- [ ] SSH preset: save a preset, confirm connectivity test blocks on bad key
- [ ] `machine_id` drift: rename a peer's `node_name`, confirm rename prompt appears in pending-presets
