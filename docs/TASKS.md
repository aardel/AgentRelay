# AgentRelay — Task List

Living checklist. Implementation status table: [feature-roadmap.md](feature-roadmap.md#implementation-status-may-2026).

## Completed (May 2026)

- [x] Local web UI served by daemon (`gui/` + pywebview shell)
- [x] Embedded terminal tabs (xterm.js + `/terminal` WebSocket)
- [x] PTY-based **Launch** (replaces tmux/external Terminal for interactive agents)
- [x] Tab close button (×) on terminal tabs
- [x] Skills panel — **Extra commands** view
- [x] **Freedom level** on launch (was YOLO checkbox); profiles in `permission_profiles.py`
- [x] Single-instance GUI lock
- [x] Desktop launcher (macOS / Windows)
- [x] `install.ps1` / `install.sh` / README
- [x] Bidirectional relay verified (Mac ↔ WINPC)
- [x] **Task queue** + **Activity** tab (SSE, Open session link) — [task-queue.md](task-queue.md)
- [x] `agent-send --profile` + `GET /api/profiles`
- [x] **SSH presets** backend + **Home** screen UI (list, add, test, discovered computers)
- [x] **Group task** tab + `/api/coordinate`
- [x] **Past chats** (`talk.py`)
- [x] **Agent notes** (resume + memory) — on branch `codex/agent-resumes-memory`
- [x] Docs: implementation status, GitHub sync guide (plain language), GUI friendly labels

## Active backlog

### Docs & onboarding

- [ ] **In-app updates** — “Check for updates” / “Get latest on this machine” (no git jargon) — [feature-roadmap.md](feature-roadmap.md#github--keeping-every-machine-on-the-same-version)
- [ ] Merge `codex/agent-resumes-memory` → `main` and sync WINPC

### GUI polish

- [ ] Freedom level when **sending** to remote agent (not only on terminal launch)
- [ ] SSH rename flow in UI (API exists; “Apply” on drift only prefills add form today)
- [ ] Remote **Open** from Activity for peer machine sessions

### Phase 2 (SSH + remote)

- [ ] Remote agent detection over SSH
- [ ] Launch agents in **remote SSH terminal** tabs
- [ ] Trust levels for peers
- [ ] Project-specific launch presets

### Cleanup

- [ ] Retire Tkinter UI when web UI has full parity
- [ ] `project_write` for Claude via settings / allowlist
- [ ] tmux optional layer (only with SSH remote attach)
- [ ] PyInstaller bundles include all modules + `gui/`

### Phase 3+

- [ ] Workflow builder, remote install over SSH, file sync, policy files, full orchestration dashboard

## Testing checklist

- [ ] `python -m unittest discover -s tests` green on Mac and WINPC
- [ ] Activity tab updates live when sending a task
- [ ] **Open** on a running task opens the right local terminal
- [ ] Freedom level: Full auto adds expected CLI flags on launch
- [ ] Group task completes (Group task tab)
- [ ] Agent notes: save resume + memory fact, reload
- [ ] SSH: test & save blocks bad key; discovered computer prompt on Home
- [ ] Get latest files on both machines after a change — [sync guide](feature-roadmap.md#github--keeping-every-machine-on-the-same-version)
