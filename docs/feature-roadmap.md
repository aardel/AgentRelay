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

## Redesigned GUI

The current GUI should evolve into a full desktop control surface.

### Main Views

- Dashboard: status of this machine, relay service, connected peers, active agents, and recent activity.
- Agents: installed/detected agent CLIs, launch profiles, running sessions, and per-agent settings.
- Terminals: integrated terminal tabs for local and remote sessions.
- Machines: local and paired remote computers, trust levels, connection status, SSH details, and capabilities.
- Orchestration: task routing, multi-agent workflows, queues, and handoffs.
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
- **SSH host GUI** — preset list, add-host dialog, connectivity status in web UI.
- Remote agent detection over SSH.
- Launch remote agents into SSH terminals.
- Trust levels for peers.
- tmux session integration (optional layer when building SSH remote attach).
- Project-specific launch presets.

### Phase 3

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

## Non-Goals For The First Pass

- Cloud-hosted coordination.
- Multi-user team permissions.
- Enterprise SSO.
- Complex visual workflow editor.
- Cross-internet relay without VPN or explicit tunneling.

