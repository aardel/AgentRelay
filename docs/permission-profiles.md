# AgentRelay Permission Profiles

Permission profiles control how much autonomy an agent is granted when launched. They replace the binary YOLO/safe toggle with a named, reusable tier system.

## Profiles

| Profile | Intent |
|---------|--------|
| `safe` | Read-only or minimal write; confirmations required for risky actions |
| `project_write` | Can edit the current project; approvals for destructive actions |
| `full_auto` | Full permissions, no confirmation prompts (previously "YOLO mode") |

## CLI Flag Mapping

Each profile maps to agent-specific CLI flags via `permission_profiles.py`:

| Agent | safe | project_write | full_auto |
|-------|------|---------------|-----------|
| claude | — | — | `--dangerously-skip-permissions` |
| codex | — | `--full-auto` | `--dangerously-bypass-approvals-and-sandbox` |
| gemini | — | — | `-y` |
| copilot | — | `--allow-all-paths` | `--allow-all` |
| cursor | — | — | `--yolo --force` |
| aider | — | — | `--yes-always` |

Note: `project_write` is only differentiated from `safe` for `codex` and `copilot`. For other agents, the profile is stored in the task record and respected in the UI, but no additional CLI flags are applied until those CLIs expose appropriate flags.

## Key Functions (`permission_profiles.py`)

```python
apply_profile_flags(argv, adapter_id, profile)  # returns modified argv
profile_for_yolo(yolo_bool)                     # backward compat: True → full_auto
is_elevated(profile)                            # True only for full_auto
profile_summary()                               # dict for /api/profiles endpoint
```

## Backward Compatibility

The `yolo=True` parameter on `relay_client.interactive_launch_argv()` still works and resolves to `full_auto`. The YOLO checkbox in the GUI passes through `profile_for_yolo()` unchanged.

## CLI Usage

```bash
agent-send --profile project_write claude@WINPC "refactor the auth module"
agent-send --profile full_auto codex@local "fix all lint errors"
```

If `--profile` is omitted, `safe` is used.

## Task Integration

Every task record carries a `permission_profile` field. The Tasks UI panel displays the profile alongside each task so it's always visible what trust level was used.

## API

```
GET /api/profiles
```

Returns the full profile summary including which agents support each tier and what flags are applied.
