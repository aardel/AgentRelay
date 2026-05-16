# AgentRelay Feature Roadmap

This document captures the next major direction for AgentRelay: a richer control app for launching, supervising, and orchestrating AI agents across local and remote machines.

## Product Goal

AgentRelay should become the control center for agent work across machines. A user should be able to open one app, see all available local and remote agents, launch them with the right permissions, route work between them, and monitor what they are doing without switching between terminals.

The system should support both cautious workflows with approvals and high-trust workflows where selected agents can run with full permissions without repeated confirmations.

## Core Principles

- Keep the user in control of trust boundaries.
- Make powerful modes explicit and visible.
- Prefer reusable launch profiles over one-off command flags.
- Treat local and remote machines as first-class execution targets.
- Provide enough logs and session history to understand what happened later.
- Make the default experience safe, but allow advanced users to opt into full automation.

## GitHub — keeping every machine on the same version

AgentRelay lives on **GitHub** so your Mac, Windows PC, and any other machine can share the same project files. Think of GitHub as a **shared project folder in the cloud** — not something you need to understand deeply to use AgentRelay day to day.

### Plain language (no git jargon)

| Instead of… | Say this |
|-------------|----------|
| pull | **Get the latest files** from GitHub onto this computer |
| push | **Send your saved changes** up to GitHub so other machines can get them |
| commit | **Save a snapshot** of what you changed (with a short note) |
| branch | **Side copy** of the project — only matters if you are experimenting; most users stay on `main` |
| merge / rebase / tree | **Ignore for now** — use the simple flow below |

**Rule of thumb:** after you change AgentRelay on one machine, **send your changes to GitHub**, then on each other machine **get the latest files**, run the installer script once, and **restart** the app.

### What you do on each computer (copy-paste friendly)

**When this machine has the newest work and the other machines need it:**

1. Save your work to GitHub (from the machine where you edited files).
2. On every other machine: get the latest files, run install, restart AgentRelay.

**Mac — get latest and run:**

```bash
cd ~/path/to/AgentRelay
git pull
./install.sh
# restart: quit AgentRelay from the menu bar / Desktop launcher, then open it again
```

**Windows — get latest and run:**

```powershell
cd C:\path\to\AgentRelay
git pull
.\install.ps1
.\scripts\install-desktop-launcher.ps1
# restart: close AgentRelay, open from Desktop shortcut again
```

> **Note:** The commands above still use `git pull` because that is what the tool expects — you can read that as **“download the newest AgentRelay files.”** A future GUI button (**Check for updates**) should run this for you with no terminal vocabulary.

### When things go wrong (simple fixes)

| Problem | What it usually means | What to try |
|---------|----------------------|-------------|
| “Already up to date” | This machine already has the newest files | Restart the app anyway if behavior still feels old |
| “Conflict” / “merge” | Two machines changed the same file differently | Ask whoever knows git to help once, or discard local doc edits and get latest again |
| App acts old after “get latest” | Daemon/GUI still running old code in memory | Fully quit AgentRelay and open it again |
| Windows and Mac out of sync | One side never got latest files | Run get-latest + install on **both**, then restart **both** |

### Roadmap: make this user-friendly in the app

- [ ] **Settings → Updates** panel: “Check for updates” / “This machine is up to date” (no `git` words in the UI).
- [ ] One-click **Get latest on this machine** (runs get-latest + install hook, shows success/failure in plain English).
- [ ] Optional reminder when a peer’s AgentRelay version looks older (compare version from `/api/status`).
- [ ] Short in-app blurb: *“GitHub keeps all your computers on the same AgentRelay build. You only need to get latest after someone changes the project.”*

**Out of scope for vibe-coder docs:** teaching branches, rebases, pull requests, or commit graphs. Link power users to standard git docs if needed.

## Implementation status (May 2026)

Legend: **Done** · **Partial** · **Not started**

| Area | Status | Notes |
|------|--------|--------|
| Daemon (relay, pairing, mDNS, dispatch, forward) | **Done** | `agentrelay.py` |
| Desktop web UI (pywebview + `gui/`) | **Done** | Default; Tkinter `--tk` fallback |
| Local live terminals (xterm + PTY) | **Done** | Mac/Linux + Windows (pywinpty) |
| Agent launch + instruction injection | **Done** | Agents + Live terminals views |
| Message send / inbox / global broadcast | **Done** | Agents + Inbox |
| Interactive delivery to open terminals | **Done** | Mac ↔ Windows verified |
| Skills installer (`/relay-send`, etc.) | **Done** | Extra commands view |
| Permission profiles (backend + CLI) | **Done** | `permission_profiles.py`, `agent-send --profile` |
| Permission level in GUI | **Partial** | “Freedom level” dropdown on launch (replaces YOLO checkbox) |
| Task queue + Activity view (SSE) | **Done** | `task_queue.py`, Activity tab |
| SSH presets (backend + API) | **Done** | `ssh_hosts.py` |
| SSH on Home screen | **Done** | List, add, test, discovered-computer prompts |
| Agent notes (resume + memory) | **Done** | `agent_data.py`, Agent notes tab (branch `codex/agent-resumes-memory`) |
| Group task (multi-agent coordinate) | **Done** | `POST /coordinate` + `/api/coordinate` |
| Past chats (talk threads) | **Done** | `talk.py`, Past chats tab |
| Remote terminal attach from other computers | **Not started** | `[attach]` opens local session only |
| Remote SSH terminal tabs | **Not started** | Presets saved; no SSH shell UI yet |
| Dedicated Machines / Permissions / Logs views | **Not started** | Folded into Home / Settings for now |
| Activity / audit log (full history) | **Not started** | Inbox + Activity cover basics |
| In-app “get latest files” (no git words) | **Not started** | Documented in GitHub section above |
| Workflow builder, file sync, policy files | **Not started** | Phase 3+ |

**Current branch note:** Agent notes + resume/memory APIs may be on `codex/agent-resumes-memory` until merged to `main`. See [TASKS.md](TASKS.md) for the live checklist.

## Redesigned GUI

The current GUI should evolve into a full desktop control surface.

### Main Views

- Dashboard: status of this machine, relay service, connected peers, active agents, and recent activity.
- **Projects:** loaded workspaces (Cursor-style) — repo root, branch, recent files, and delegation targets for the active project.
- Agents: installed/detected agent CLIs, launch profiles, running sessions, and per-agent settings.
- Terminals: integrated terminal tabs for local and remote sessions.
- Machines: local and paired remote computers, trust levels, connection status, SSH details, and capabilities.
- Orchestration: task routing, multi-agent workflows, queues, and handoffs.
- **GitHub:** linked repos, PRs, issues, Actions status, and agent tasks tied to branches/commits.
- Permissions: launch profiles, allowlists, denylists, approval memory, and safety controls.
- Logs: command history, relay events, forwarded tasks, errors, and session transcripts.
- Settings: app configuration, network, agent paths, defaults, and backup/export options.

### GUI Requirements

- Modern layout with sidebar navigation.
- Clear status indicators for relay, peers, agents, SSH sessions, and permission level.
- Agent cards with launch, stop, restart, open terminal, and view logs actions.
- Machine cards showing hostname, IP, relay status, SSH status, trust level, and available agents.
- Command preview before launching agents.
- Visible warning when an agent is running with elevated or full permissions.
- Emergency stop control for all agents launched by AgentRelay.
- Search/filter for agents, machines, terminals, and logs.

## Integrated Terminals

AgentRelay should include terminal panes so agent sessions can be launched and monitored inside the GUI.

### Terminal Features

- Local terminal tabs.
- Remote SSH terminal tabs.
- Named sessions for Codex, Claude, Gemini, and other agents.
- Split panes for side-by-side local and remote work.
- Session restore after app restart where possible.
- Terminal output search.
- Copy selected output.
- Send text to an active terminal session.
- Launch an agent into a selected terminal.
- Attach to existing tmux sessions such as `agentrelay-codex`.
- **Usage strip under each terminal tab** (when the agent supports it) — see below.

### Terminal Usage & Token Estimates

Show a compact **usage bar beneath each agent terminal** (not inside the xterm scrollback) so quota and pacing are visible without parsing raw CLI output.

#### What to display (per session)

| Field | Source | Notes |
|-------|--------|--------|
| **Tokens used (session)** | Agent-reported or parsed from stdout | Reset when tab/session restarts |
| **Tokens remaining** | Agent API/status line if exposed | Hide when unknown |
| **Context / window size** | Agent-reported max context | e.g. 200k — helps interpret “remaining” |
| **Estimated time to finish** | Derived | `(remaining_tokens / rolling_tokens_per_minute)` from user’s recent rate on this agent |
| **Rolling usage rate** | AgentRelay-computed | Exponential moving average of tokens/min over last N minutes of active generation |

#### Agent support matrix (expected)

| Agent | Native usage reporting | Fallback |
|-------|------------------------|----------|
| Claude Code | Status/footer when CLI exposes usage | Parse structured status lines if documented |
| Codex | Session usage when available | Parse `tokens` / rate lines from output |
| Gemini | Model quota hints if CLI prints them | Same |
| Custom | Via adapter hook | Manual refresh only |

Adapters declare `usage_reporting: native | parse | none` in config so the UI knows whether to poll, parse PTY output, or show “usage not available.”

#### UI behavior

- Bar sits **below the xterm panel**, one row per terminal tab: `Used 42k · Left ~158k · ~12 min at current pace`.
- **Pace indicator** — compare current rate to user’s 7-day average for this agent; show “slower / typical / faster than usual.”
- **Warnings** — soft alert when remaining < 10% of context or estimated finish crosses a user-defined session budget.
- **Hover / expand** — sparkline of tokens/min for this session; link to Logs for full history.
- **Multi-machine** — usage is per terminal session on each node; dashboard can sum by project when project workspace is loaded.

#### Implementation approach (proposed)

1. **PTY tap** — optional parser on terminal output stream for known patterns (regex per agent), feeding a `session_usage` struct on the daemon.
2. **Adapter poll** — for agents with a side-channel status command or JSON status file, poll every 30s while session is active.
3. **User calibration** — store per-agent `tokens_per_minute` EMA in `~/.config/agentrelay/usage_stats.json` (local only) to improve ETA when the agent does not report remaining tokens (estimate from context size minus parsed usage).
4. **WebSocket push** — extend `/terminal` or add `/api/sessions/{id}/usage` + SSE so the usage bar updates without polling.
5. **Privacy** — usage stats stay local unless user opts in to sync across their machines.

#### API (proposed)

- `GET /api/terminal/sessions/{session_id}/usage` — `{ used, remaining, limit, tokens_per_minute, eta_seconds, source }`
- `GET /api/usage/agents/{agent_id}/history` — rolling averages for dashboard

### Terminal Backend Options

- Local pseudo-terminal support through Python PTY APIs.
- Optional tmux integration for durable sessions.
- SSH-backed terminal sessions for remote machines.
- Web terminal component if the GUI moves to a webview or browser-based UI.

## SSH Support

SSH should be a first-class connection type alongside relay peer discovery.

### Peer-to-Preset Flow (Designed 2026-05)

When a new relay peer is discovered, AgentRelay offers to save it as an SSH preset:

1. `handle_peer_announce` receives a node not already saved as an SSH preset.
2. GUI notification: "New peer: WINPC (192.168.1.186) — Save as SSH target?"
3. Pre-fill host/IP from peer registry (editable — multi-NIC/NAT may differ).
4. User enters SSH username and key path only (no passphrase storage).
5. Connectivity test on save: `ssh -o ConnectTimeout=5 -o BatchMode=yes user@host 'echo ok'` — fail loudly, do not save broken presets.
6. Write entry to `~/.config/agentrelay/ssh_hosts.json`.

**Join key:** `node_name` (primary, matches `tasks.target_node` and peer registry) + `machine_id` (drift detector). If `node_name` changes between announces, prompt to update the preset rather than creating a duplicate.

`machine_id` sources: Linux `/etc/machine-id`, Mac `ioreg IOPlatformUUID`, Windows `wmic csproduct get UUID`. Included in the `/peer-announce` payload.

**Storage:** `~/.config/agentrelay/ssh_hosts.json` (separate from `config.yaml`, `chmod 600`, git-ignored). Keys must be passphrase-less or in `ssh-agent`. **Reconnect deduplication:** check existing presets by `node_name` before firing the notification.

### SSH Connection Features

- Add/edit/remove SSH hosts via `ssh_hosts.json`, with pre-fill from relay peer registry.
- Key auth only (passphrase-less or via `ssh-agent`).
- Connectivity test on save (fail loudly, not silently).
- Known-host verification.
- `machine_id` drift detection with rename prompt.
- Reconnect deduplication (no repeat save prompts for known peers).
- Remote shell detection.
- Remote working directory defaults.
- Remote agent detection.
- Remote file path mapping.
- Optional port forwarding for relay or auxiliary services.

### SSH Machine Capabilities

For each SSH host, AgentRelay should be able to detect:

- OS and architecture.
- Available shells.
- Installed agent CLIs.
- Python/node/git availability.
- Whether AgentRelay is installed.
- Whether the relay service is running.
- Available project folders.
- tmux availability.

## Local and Remote Orchestration

The app should coordinate tasks across machines and agents, not only forward one-off messages.

### Orchestration Features

- Send a task to a selected local or remote agent.
- Route tasks based on machine capabilities.
- Hand off work from one agent to another.
- Queue tasks when a remote machine is offline.
- Track task state: queued, sent, acknowledged, running, completed, failed.
- Attach files or project context to a task.
- Show task timeline across machines.
- Support local-to-remote and remote-to-local responses.
- Allow workflows such as:
  - Mac agent handles Xcode/iOS work.
  - Windows agent handles Windows builds.
  - Linux server handles Docker or deployment checks.
  - Local coordinator agent reviews and integrates results.

### Workflow Builder

Future versions can add saved workflow templates:

- Run tests on all machines.
- Build on target OS.
- Ask remote agent to inspect logs.
- Deploy to staging.
- Review code changes.
- Fix CI failure.
- Sync project files before task.

## Project Workspace (Cursor-Style)

AgentRelay should let users **load a complete project** as the working context — similar to opening a folder in Cursor — then delegate work to local or remote agents against that project, not only send one-off messages.

### Goals

- One active (or pinned) project per machine defines default `cwd`, git context, and what gets attached to relay tasks.
- Agents launched from a loaded project start in the project root (or a configured subfolder) with AgentRelay instructions scoped to that repo.
- Delegation routes subtasks to the right peer/agent (e.g. Mac for iOS, Windows for .NET) while keeping a single project identity across machines.

### Load Project Flow

1. **Open project** — pick a local folder or clone from Git URL; validate git repo (optional but recommended).
2. **Index lightweight metadata** — root path, default branch, remotes, last commit, dirty/clean status, detected stack (package.json, pyproject.toml, etc.).
3. **Bind to relay** — store in `~/.config/agentrelay/projects.json` (or per-project `.agentrelay/project.yaml`); show in **Projects** sidebar.
4. **Launch agents in project context** — PTY sessions use project `cwd`; `agent-send` / tasks include `project_id` and paths relative to root.
5. **Delegate** — from the Projects view or orchestration panel: assign a task to `codex@WINPC` or `claude@Mac` with project path hints and permission profile.

### Project Features

- Recent and pinned projects list; quick switch (like Cursor’s recent workspaces).
- Per-project launch presets (default agent, profile, trusted peers for this repo).
- Per-project rules snippet (coding standards, test command, deploy notes) injected with AgentRelay instructions.
- Multi-machine project sync: same logical project on Mac + Windows (shared git remote; optional path map when roots differ).
- Attach project context to tasks (branch, changed files summary, link to GitHub PR/issue when integrated).
- “Open in agent” actions: send selection, file path, or diff to local/remote agent terminal.
- Emergency scope: permission profiles respect project root as filesystem boundary where possible.

### Storage (proposed)

- **Registry:** `~/.config/agentrelay/projects.json` — id, name, local_path, remote_paths map, github_repo, last_opened.
- **Optional in-repo:** `.agentrelay/project.yaml` — team-shared defaults (ignored paths, default agent, CI command).

## GitHub Integration

First-class GitHub support so relay tasks, projects, and agents align with real repo workflow — not a separate “GitHub app,” but hooks into the loaded project and orchestration layer.

### Authentication

- OAuth (device flow or browser) or fine-grained PAT stored in OS keychain / credential store — never in `config.yaml` or git.
- Scopes: repo read, issues, pull requests, Actions read (write optional, behind explicit opt-in).

### Core Features

- **Link project to GitHub** — `owner/repo` on load or from `git remote get-url origin`.
- **Repo browser** — branches, default branch, open PRs/issues count on project card.
- **PR-aware delegation** — “Implement review comments on PR #42” → task includes PR number, head branch, and diff summary for the target agent.
- **Issue → task** — create or assign relay task from issue title/body; post status/comments back when done (optional).
- **Actions visibility** — show latest workflow run status on project dashboard; trigger re-run or notify agent on failure (read-first).
- **Branch context** — agents default to current branch; warn on uncommitted changes before full-auto sessions.
- **Compare / delegate by platform** — e.g. open PR from Mac agent, run Windows build check on WINPC peer via relay.

### API Surface (proposed)

- `GET/POST /api/projects` — list/load/register projects.
- `GET /api/projects/{id}/git-status` — branch, dirty files, last commit.
- `GET/POST /api/github/link` — connect account, list repos for picker.
- `GET /api/github/repos/{owner}/{repo}/prs|issues|actions` — cached summaries for UI.
- `POST /api/tasks` — accept optional `project_id`, `github_pr`, `github_issue` fields.

### Safety

- Never exfiltrate tokens to remote peers; GitHub calls stay on the machine that holds the credential.
- Remote delegation sends **task text + paths**, not GitHub tokens.
- Audit log records GitHub-linked actions (PR comment, check run) per project.

## Permission Profiles

AgentRelay should support reusable permission profiles for launching agents.

### Built-In Profiles

- Safe: read-only or minimal write access, confirmations required.
- Project Write: can edit the current project, approvals for risky actions.
- Trusted Local: broad local workspace access, fewer confirmations.
- Full Auto: full permissions without confirmation prompts.
- Remote Safe: SSH access with limited commands and confirmations.
- Remote Full Auto: trusted remote automation without confirmation prompts.

### Profile Settings

Each profile should define:

- Filesystem scope.
- Network access.
- GUI/app control.
- Shell command approval mode.
- Command allowlist.
- Command denylist.
- Secret path protections.
- Environment variables.
- Agent-specific launch flags.
- Logging level.
- Session timeout.

### Safety Controls

- Require an explicit opt-in for full auto profiles.
- Show elevated sessions prominently.
- Emergency stop for all elevated agents.
- Optional time-limited elevation.
- Optional snapshot or git status check before starting a full auto session.
- Keep an audit log of commands and forwarded tasks.

## Agent Launch Management

AgentRelay should detect and launch common agent CLIs.

### Supported Agents

- Codex.
- Claude.
- Gemini.
- Future custom agents via user-defined launch commands.

### Launch Features

- Detect installed agent CLI paths.
- Configure per-agent default launch profiles.
- Save launch presets per project.
- Start in selected directory.
- Start inside integrated terminal.
- Start inside tmux.
- Restart crashed sessions.
- Show exact command before launch.
- Copy launch command.
- Inject AgentRelay instructions automatically.

## Remote Agent Management

For remote machines, AgentRelay should support both relay-native and SSH-native control.

### Remote Modes

- Relay mode: communicate with another AgentRelay service over the local network.
- SSH mode: connect directly to a remote host and run commands.
- Hybrid mode: use SSH to install/start AgentRelay, then use relay for normal task routing.

### Remote Setup Features

- Install AgentRelay on a remote host over SSH.
- Start/stop/restart remote relay service.
- Launch remote GUI where supported.
- Launch remote agent terminal sessions.
- Sync AgentRelay config or pairing information.
- Verify remote health.

## Activity and Audit Log

The app should keep a durable record of important activity.

### Logged Events

- Agent launches.
- Permission profile used.
- Commands sent through AgentRelay.
- Remote SSH commands.
- Pairing and trust changes.
- Task routing events.
- Approval prompts and decisions.
- Service starts/stops/restarts.
- Errors and crashes.

## Suggested MVP

The first implementation pass should focus on high-value foundations.

1. Redesigned GUI shell with sidebar navigation.
2. Agent launch profiles.
3. Integrated local terminal tabs.
4. Basic SSH host manager.
5. Remote SSH terminal tabs.
6. Agent launch into local terminal.
7. Command preview for launches.
8. Activity log.
9. Emergency stop.
10. Permission profile model with Safe, Project Write, and Full Auto.

## Later Phases

### Phase 2

- ~~Task queue and task status tracking.~~ **Done (2026-05)** — SQLite `tasks.db`, full originator+receiver lifecycle, SSE-driven Tasks UI panel, `[attach]` links. See [docs/task-queue.md](task-queue.md).
- ~~Permission profiles (Safe / Project Write / Full Auto).~~ **Done (2026-05)** — `permission_profiles.py`, `--profile` on `agent-send`. See [docs/permission-profiles.md](permission-profiles.md).
- ~~SSH preset backend~~ **Done (2026-05)** — `ssh_hosts.py`, `/api/ssh-hosts`, `machine_id` in peer announce, pending-preset notifications.
- ~~SSH host GUI (basic)~~ **Done (2026-05)** — Home screen: preset list, add computer, test & save, discovered-computer prompts. Dedicated “Machines” view still optional.
- ~~Agent resumes + memory~~ **Done (2026-05)** — `agent_data.py`, Agent notes tab (merge to `main` pending).
- ~~Multi-agent coordination GUI~~ **Done (2026-05)** — Group task tab; `/api/coordinate` alias.
- **Permission level in GUI** — freedom dropdown on launch; send-from-GUI profile picker still optional.
- Remote agent detection over SSH.
- Launch remote agents into SSH terminals.
- Trust levels for peers.
- tmux session integration (optional layer when building SSH remote attach).
- **Load project (MVP)** — open folder, bind `cwd` to terminals/tasks, recent projects list.
- Project-specific launch presets and per-project AgentRelay rules snippet.
- **Terminal usage bar (MVP)** — parse or native usage where supported; show used/remaining; basic tokens/min EMA.

### Phase 3

- **Project workspace (full)** — multi-machine path map, delegate-from-project UI, “open in agent” for files/diffs.
- **GitHub integration (MVP)** — OAuth/PAT, link repo to project, branch status, PR/issue picker on send.
- **GitHub integration (full)** — PR/issue-linked tasks, Actions dashboard, optional comment/check updates.
- **Terminal usage (full)** — ETA from rolling rate, pace vs historical average, warnings, per-project usage totals.
- Workflow builder.
- Remote AgentRelay install/start over SSH.
- File sync support.
- Rich transcript viewer.
- Policy file support through `.agentrelay-policy.yaml`.
- Full orchestration dashboard.

### Phase 4

- Multi-machine build/test workflows.
- Plugin system for custom agents and tools.
- Secure credential storage integration.
- Signed peer requests.
- Team/shared machine support.

## Architecture Decision (2026-05)

**Chosen path:** one installable app per OS with an **embedded local web UI** served by the existing `agentrelay` daemon (`aiohttp` on `localhost`).

- **Shell:** `pywebview` (WebView2 / WebKit / GTK) — not a cloud-hosted website.
- **UI:** HTML/CSS/JS in `gui/`, including integrated **xterm.js** tabs wired to `/terminal`.
- **Daemon:** unchanged role — mDNS, pairing, dispatch, PTY sessions; also serves static UI and `/api/*`.
- **Legacy:** Tkinter UI remains available via `agentrelay-gui --tk` until the web shell is fully equivalent.

Each machine runs the full stack. Remote peers use the relay protocol; remote terminal viewing uses read-only WebSocket attach (see `TERMINAL_PROTOCOL.md`).

## Open Design Questions

- ~~Should the redesigned GUI remain Tkinter, or move to a richer stack such as Qt, Tauri, Electron, or a local web UI?~~ **Resolved:** local web UI in pywebview (see above).
- ~~How should full-auto permissions map to each supported agent CLI?~~ **Resolved:** `permission_profiles.py` with per-agent translation table. See [docs/permission-profiles.md](permission-profiles.md).
- ~~What is the safest default storage for SSH credentials on macOS, Windows, and Linux?~~ **Resolved:** `ssh_hosts.json` alongside `tasks.db` (`chmod 600`, git-ignored). Key-based auth only; connectivity tested on save.
- ~~Should task history live in local files, SQLite, or another embedded database?~~ **Resolved:** SQLite (`tasks.db`, WAL mode). See [docs/task-queue.md](task-queue.md).
- Should integrated terminals standardize on tmux first, or keep PTY direct? **Current lean:** keep PTY direct; add tmux as optional layer only when building SSH remote attach.
- Should orchestration be centralized on one coordinator machine or distributed across all paired machines? **Current lean:** distributed task queue may be sufficient until real multi-machine workflows emerge.
- Where should “project rules” live — global, per-project file (`.agentrelay/project.yaml`), or both? **Current lean:** per-project file for team shareability, with global defaults in config.
- GitHub: OAuth app vs PAT-only for v1? **Current lean:** PAT + keychain for MVP; OAuth device flow when UI login is built.
- Token ETA when agents do not report `remaining`: trust parsed usage only, or blend with user’s historical tokens/min? **Current lean:** blend with local EMA; show “estimated” badge when not agent-native.

## Non-Goals For The First Pass

- Cloud-hosted coordination.
- Multi-user team permissions.
- Enterprise SSO.
- Complex visual workflow editor.
- Cross-internet relay without VPN or explicit tunneling.

