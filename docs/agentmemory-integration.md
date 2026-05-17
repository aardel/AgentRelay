# agentmemory integration (optional sidecar)

AgentRelay keeps **relay-specific** notes in `agent_data.py` (resume markdown + memory JSON per agent). For deep, automatic session memory (tool-use capture, hybrid search, replay), you can run [agentmemory](https://github.com/rohitg00/agentmemory) alongside AgentRelay.

## Roles

| System | Purpose |
|--------|---------|
| **AgentRelay resume/memory** | Identity, delegation prefs, peer facts — edited in **Agent notes** or via `/api/agents/{id}/resume` and `/memory` |
| **agentmemory** | Auto-captured observations, semantic recall, session replay — separate Node + iii-engine service |

They complement each other; AgentRelay does not replace agentmemory with files alone.

## Quick setup (Windows)

### 1. Install agentmemory + iii-engine

```powershell
# Terminal A — memory server (REST :3111, viewer :3113)
npx -y @agentmemory/agentmemory@latest

# Verify
curl http://127.0.0.1:3111/agentmemory/health
```

On Windows you also need **iii-engine v0.11.2** (prebuilt binary or Docker). See the [agentmemory Windows section](https://github.com/rohitg00/agentmemory#windows).

### 2. Wire agents via MCP (recommended)

Add to your agent MCP config (Cursor, Claude Desktop, Gemini CLI, etc.):

```json
{
  "mcpServers": {
    "agentmemory": {
      "command": "npx",
      "args": ["-y", "@agentmemory/mcp"],
      "env": {
        "AGENTMEMORY_URL": "http://127.0.0.1:3111"
      }
    }
  }
}
```

Claude Code / Codex: use `agentmemory connect claude-code` or `codex plugin install agentmemory` per upstream docs.

### 3. Enable the AgentRelay bridge

In `config.yaml` (or `~/.config/agentrelay/config.yaml`):

```yaml
agentmemory:
  enabled: true
  url: http://127.0.0.1:3111
  # secret: ""   # optional; matches AGENTMEMORY_SECRET on the server
  project: agentrelay
  token_budget: 1500
  inject_on_launch: true    # smart-search → launch snippet
  observe_on_close: true      # PTY scrollback tail → observe on exit
  timeout_seconds: 3
```

Restart the AgentRelay daemon/GUI.

## What the bridge does

When `agentmemory.enabled: true` and the server is reachable:

1. **On terminal launch** — `POST /agentmemory/smart-search` with a query derived from the agent id and node name; top hits are prepended to the launch snippet under `## Project memory (agentmemory)`.
2. **On PTY close** — `POST /agentmemory/observe` with a short summary and the last ~12KB of terminal output (ANSI stripped).
3. **Status API** — `GET /api/status` includes `agentmemory: { enabled, reachable, url, project }`.

Failures are logged at debug level and do not block terminals.

## Agent notes vs agentmemory

- Use **Agent notes** for: “I prefer codex@WINPC for edits”, relay URLs, stable identity.
- Use **agentmemory** for: what happened in past coding sessions, file patterns, architecture discovered from tool use.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `reachable: false` in status | Is `npx @agentmemory/agentmemory` running? `curl` health URL |
| No project memory in snippet | `inject_on_launch: true`, server up, try a seeded `agentmemory demo` |
| MCP shows only 7 tools | Start full server; set `AGENTMEMORY_URL` in MCP env |
| Windows engine errors | Install iii v0.11.2 binary or use Docker per upstream README |

## License

agentmemory is Apache-2.0. AgentRelay’s bridge (`agentmemory_bridge.py`) is part of this repo and only talks to a locally running server you install separately.
