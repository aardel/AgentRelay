# AgentRelay Changelog

## [Unreleased] — May 2026

### Added

#### Task Queue (`task_queue.py`)
- SQLite-backed persistent task queue at `~/.config/agentrelay/tasks.db` (WAL mode).
- Dual-record design: originator keeps a `queued → sent → completed/failed` record; receiver keeps a `received → running → completed/failed` record, both joined by `task_id` + `originator_task_id`.
- `reply_to` URL derived from `request.remote` on the receiver side — no IP resolution needed on the originator.
- Schema: `id`, `created_at`, `updated_at`, `source_node`, `source_agent`, `target_node`, `target_agent`, `message`, `status`, `permission_profile`, `session_id`, `originator_task_id`, `reply_to`, `result`, `error`, `retry_count`.
- Migration column addition for existing databases (`_MIGRATE_COLS`).
- Methods: `create`, `update_status`, `ack`, `mark_running`, `complete`, `fail`, `requeue`, `get`, `list_tasks`, `pending_for_peer`, `prune`.
- Thread-safe via `asyncio.Lock` + `run_in_executor`.

#### Task Wiring in `agentrelay.py`
- `handle_forward` now extracts `task_id` / `reply_to` from the relay payload, creates a receiver task record (`status='received'`), calls `mark_running` once a PTY launches, and registers `_on_close` on the PTY session to mark completion.
- `_on_session_closed` callback: marks task `completed` or `failed`, fires SSE notification, POSTs status back to originator via `_push_status_callback`.
- `handle_task_status` (POST `/api/tasks/{id}/status`): token-authenticated endpoint for the originator's incoming callback from the receiver — updates status and triggers SSE.
- New API endpoints: `GET /api/tasks`, `GET /api/tasks/events` (SSE), `GET /api/tasks/{id}`, `POST /api/tasks/{id}/status`.

#### Task Wiring in `agent-send`
- Remote sends now create a local `queued` task record, update it to `sent` on delivery success or `failed` on error.
- `--profile` flag (choices: `safe`, `project_write`, `full_auto`) records the permission profile with the task.
- `task_id` included in the JSON output.

#### SSE Push for Task Events (`agentrelay.py`)
- `_task_event_queues`: list of per-connection `asyncio.Queue` instances.
- `_notify_task_event(task_id, status)`: push to all subscribers.
- `handle_task_events`: `GET /api/tasks/events` streams `data: {...}` events with 15 s keepalive.

#### Tasks UI Panel (`gui/app.js`, `gui/index.html`, `gui/style.css`)
- Tasks nav item in sidebar.
- `initTasksPanel()`: creates `EventSource` at `/api/tasks/events`; instant refresh on task-changed events.
- `fetchTasks()`: polls `/api/tasks?limit=50`; reschedules 2 s timer only while active tasks exist.
- `renderTasks(tasks)`: 7-column table — Status (color-coded badge), Target, Agent, Message, Age, Duration, Session.
- `[attach]` link in Session column: opens embedded xterm.js terminal for a running or completed task's `session_id`.
- Duration shows live elapsed time for `running` tasks; final duration for completed.
- `.tasks-table`, `.task-badge`, `.task-msg` styles in `style.css`.

#### Permission Profiles (`permission_profiles.py`)
- Three tiers: `safe` (default, no extra flags), `project_write` (auto-approve file ops), `full_auto` (no confirmation prompts).
- Per-agent CLI flag mappings: `project_write` adds `--full-auto` for Codex and `--allow-all-paths` for Copilot; other agents fall back to safe with a settings-file note.
- `full_auto` reuses `YOLO_FLAGS` from `yolo_flags.py`.
- `apply_profile_flags(argv, adapter_id, profile)` inserts flags after `argv[0]`.
- `profile_for_yolo(yolo)`, `is_elevated(profile)`, `profile_label(profile)`, `profile_note(profile, agent_family)`, `profile_summary()`.
- `GET /api/profiles` endpoint serves profile definitions to the GUI.
- `relay_client.interactive_launch_argv` updated to use `apply_profile_flags` via `permission_profiles`.

#### PTY Session Hooks (`pty_session.py`)
- `_on_close(session_id, reason)` callback invoked on both `stop()` and `_watch_exit()`.
- Enables the daemon to mark a task complete/failed when the agent process exits.

#### SSH Host Presets (`ssh_hosts.py`) — **New in this build**
- `SSHHost` dataclass: `node_name`, `host`, `user`, `port`, `key_path`, `machine_id`, `added_at`, `last_ok`.
- `SSHHostStore`: JSON-backed store at `~/.config/agentrelay/ssh_hosts.json` (chmod 600, separate from `config.yaml`).
  - `list`, `get`, `get_by_machine_id`, `save`, `update_last_ok`, `delete`, `rename_node`, `has_preset`.
  - Atomic save via `.tmp` → rename.
- `get_machine_id()`: platform-aware stable UUID (Linux: `/etc/machine-id`, Mac: `ioreg` UUID, Windows: `wmic csproduct get UUID`).
- `test_ssh_connectivity(host, user, port, key_path)`: runs `ssh -o BatchMode=yes … echo ok`; returns `(ok, message)`. Fails loudly at save time.

#### SSH Host API (`agentrelay.py`) — **New in this build**
- `GET /api/ssh-hosts` — list saved presets (localhost-only).
- `POST /api/ssh-hosts` — save new/updated preset after connectivity test. Fails with `{ok: false, message}` if test fails.
- `DELETE /api/ssh-hosts/{node}` — remove preset.
- `POST /api/ssh-hosts/{node}/test` — re-run connectivity test, update `last_ok` on success.
- `POST /api/ssh-hosts/{node}/rename` — apply a drift-detected rename (updates `node_name` in preset).
- `GET /api/ssh-hosts/pending-presets` — returns and clears pending save/rename notifications for the GUI.

#### Peer-to-Preset Flow (`agentrelay.py`) — **New in this build**
- `machine_id` field added to `/peer-announce` payload (sent by `_announce_to_peer`).
- `handle_peer_announce` now checks `ssh_hosts.json` after each announce:
  - If `machine_id` matches an existing preset with a *different* `node_name` → queues a `rename` notification.
  - If neither `node_name` nor `machine_id` matches any preset → queues a `new` notification (deduplicated).
- GUI polls `GET /api/ssh-hosts/pending-presets` to show "New peer — save as SSH target?" prompts.
- `_pending_ssh_presets` module-level list (cleared on read, like `_gui_delivery_queue`).

#### Feature Roadmap (`docs/feature-roadmap.md`)
- SSH Support section fully rewritten: 6-step peer-to-preset flow, join key design (`node_name` + `machine_id`), `ssh_hosts.json` rationale.
- Phase 2: task queue items marked Done 2026-05. SSH items broken out with machine_id drift detection and connectivity test.
- Three open design questions marked resolved.

### Changed

- `relay_client.deliver_to_peer` / `forward_to_peer`: accept optional `task_id` and `reply_to` kwargs and include them in the relay payload.
- `agent-send cmd_send`: creates and updates task records around the `deliver_to_peer` call.
- `agentrelay._announce_to_peer`: includes `machine_id` in the outgoing payload.
- `agentrelay.handle_peer_announce`: reads `machine_id`; drives SSH pending-preset logic.
- `agentrelay.build_app`: registers all new `/api/tasks/*` and `/api/ssh-hosts/*` routes.

### Architecture Notes

- **Task queue singleton**: lazy-init `_task_queue` at module level; safe for unit tests (no filesystem touch on import).
- **SSH presets**: key-based auth only — no passphrase storage; require `ssh-agent` for passphrase-protected keys.
- **Distributed orchestration**: each machine keeps its own task records. No central coordinator. The `reply_to` URL plus `originator_task_id` form a lightweight callback chain.
- **Two-way relay tested**: WINPC ↔ Mac two-way relay messaging confirmed working before this build.
