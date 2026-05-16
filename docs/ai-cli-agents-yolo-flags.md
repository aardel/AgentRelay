# AI Coding Agents — YOLO / Skip-Permissions Flags Reference

> Equivalents to Claude Code's `--dangerously-skip-permissions` across major AI coding agents.
> **Last updated:** May 2026

---

## Quick Reference Table

| Agent | Flag / Toggle | Headless-ready? |
|---|---|---|
| **Claude Code** | `--dangerously-skip-permissions` | ✅ Yes |
| **OpenAI Codex CLI** | `--dangerously-bypass-approvals-and-sandbox` | ✅ Yes |
| **Gemini CLI** | `-y` / `--yolo` (interactive: `Ctrl+Y`) | ✅ Yes |
| **GitHub Copilot CLI** | `--allow-all` (+ `--autopilot` for full autonomy) | ✅ Yes |
| **Cursor CLI** (`cursor-agent`) | `--yolo` + `--force` | ⚠️ Needs TTY (use tmux) |
| **Aider** | `--yes-always` | ✅ Yes |
| **Cline** (VS Code) | GUI toggle — "Auto-approve / YOLO Mode" | ❌ GUI only |
| **Cursor IDE** | Settings → Chat → Auto-Run | ❌ GUI only |
| **Windsurf** | Cascade → Turbo Mode toggle | ❌ GUI only |
| **GitHub Copilot in VS Code** | `/yolo` or `/autoApprove` in chat | ❌ GUI only |
| **Zed Agent** | Per-thread auto-approve toggle | ❌ GUI only |

---

## CLI Agents — Detailed

### 1. Claude Code (Anthropic)

```bash
claude --dangerously-skip-permissions
```

**Aliases for interactive use:**
```bash
claude -p "task" --dangerously-skip-permissions    # one-shot print mode
```

**Persistence:** Not persistent — must pass each session, or alias it.

**Safer alternative (2026):** `auto` mode — a classifier reviews each tool call and blocks risky actions (mass file ops, exfiltration). Currently in research preview for Team plan users.

---

### 2. OpenAI Codex CLI

```bash
codex --dangerously-bypass-approvals-and-sandbox "task"
```

**Less nuclear option (keeps sandbox):**
```bash
codex --full-auto "task"
```

**In-TUI toggle:** Default / Full Access mode switcher.

---

### 3. Google Gemini CLI

```bash
gemini -y -p "task"          # short flag
gemini --yolo -p "task"      # long flag
```

**Interactive toggle:** `Ctrl + Y` inside the TUI (shows "YOLO Mode" indicator).

**Note:** Gemini CLI does not parse chained commands as carefully as Claude/Codex — extra caution warranted in YOLO mode.

---

### 4. GitHub Copilot CLI

```bash
copilot --allow-all                              # skip all permission prompts
copilot --allow-all --autopilot -p "task"        # full autonomy + skip prompts
```

**Slash commands during a session:**
- `/allow-all` — grant full permissions mid-session
- `/yolo` — alias for `/allow-all`
- `/autopilot` — enter autopilot mode

**Granular alternatives:**
- `--allow-all-paths` — skip path approvals only
- `--allow-all-urls` — skip URL approvals only
- `--disallow-temp-dir` — block `/tmp` access

---

### 5. Cursor CLI (`cursor-agent`)

```bash
cursor-agent --yolo --force -p "task"
```

**What each flag does:**
- `-p` — print/headless mode (non-interactive)
- `--force` — auto-apply file changes; implicitly trusts the workspace
- `--yolo` — workspace trust + auto-run + skip MCP prompts + web tools on

**Persistent config alternative** — edit `~/.cursor/config.json`:
```json
{
  "approvalMode": "unrestricted"
}
```
With this set, `--force` is no longer required.

**⚠️ TTY gotcha:** Cursor CLI requires a real TTY. Direct execution from scripts/cron hangs indefinitely. Wrap in tmux:
```bash
tmux new-session -d -s cursor "cursor-agent -p --force --yolo 'task'"
```

---

### 6. Aider

```bash
aider --yes-always           # current
aider --yes                  # older versions
```

Auto-confirms every prompt. Combine with `--auto-commits` for full hands-off.

---

## IDE Agents (GUI-only, for completeness)

### Cline (VS Code extension)
- **Toggle:** Auto-approve / YOLO Mode checkbox in settings panel
- **Granularity:** Per tool category (read, edit, execute, browse)
- **Enterprise control:** Admins can disable YOLO via remote config JSON

### Cursor IDE
- **Path:** Settings → Chat → Auto-Run (older name: "YOLO mode")
- **Shortcut:** `⌘/Ctrl + Shift + J` opens settings
- **Features:** Command allowlist/denylist, delete-file protection toggle

### Windsurf (Codeium)
- **Toggle:** Cascade chat pane → Turbo Mode

### GitHub Copilot in VS Code
- **Slash commands:** `/yolo` or `/autoApprove` in chat input
- **Granular settings (settings.json):**
  ```json
  "chat.tools.terminal.autoApprove": {
    "bash": true,
    "git": true,
    "ls": true,
    "rm": false,
    "git push": false
  },
  "chat.tools.urls.autoApprove": {
    "https://*.github.com": true,
    "https://stackoverflow.com": true
  }
  ```

### Zed Agent
- **Toggle:** Per-thread auto-approve in agent panel

---

## Recommended Shell Aliases

Add to `~/.zshrc` or `~/.bashrc`:

```bash
# --- CLAUDE CODE ---
alias claude-yolo='claude --dangerously-skip-permissions'

# --- CODEX CLI ---
alias codex-yolo='codex --dangerously-bypass-approvals-and-sandbox'
alias codex-auto='codex --full-auto'

# --- GEMINI CLI ---
alias gem-yolo='gemini -y'

# --- COPILOT CLI ---
alias copilot-yolo='copilot --allow-all --autopilot'

# --- CURSOR CLI ---
alias cursor-yolo='cursor-agent --yolo'
alias cursor-headless='cursor-agent -p --force --yolo'

# --- AIDER ---
alias aider-yolo='aider --yes-always --auto-commits'
```

---

## ⚠️ Safety Recommendations

**YOLO mode bites hardest in these scenarios:**
1. **Prompt injection via repo files** — a poisoned `README.md`, `CLAUDE.md`, `AGENTS.md`, or `.cursor/rules` in any cloned repo can instruct the agent to run arbitrary shell commands, which YOLO mode will execute without asking.
2. **Shared environments** — databases, ports, and state can be wrecked across branches.
3. **Wide filesystem access** — agents can "clean up" what they perceive as test data, or modify files outside the intended scope.

**Mitigations (in increasing order of safety):**
1. **Shell alias with reminder name** (`-yolo` suffix) — at least you know you're in dangerous mode.
2. **Dedicated working directory** — restrict the agent to a sandboxed project folder.
3. **Docker dev container** — isolate the entire toolchain.
4. **Separate VM or throwaway user account** — for truly hostile or untrusted code.
5. **CI runner / ephemeral cloud instance** — best for fully autonomous jobs.

**Universally bad combinations:**
- YOLO mode + cloning untrusted repos
- YOLO mode + running in `$HOME` directly
- YOLO mode + access to production credentials in `.env`
- YOLO mode + agent loops with no time/cost limit

---

## Cross-Agent Equivalence Cheat Sheet

| What you want | Claude | Codex | Gemini | Copilot | Cursor |
|---|---|---|---|---|---|
| Skip all approvals | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `-y` | `--allow-all` | `--yolo --force` |
| Run task & exit | `-p` | `exec` | `-p` | `-p` | `-p` |
| Full autonomy (multi-step) | (default with above flag) | (default with above flag) | (default with above flag) | `--autopilot` | (default with above flags) |
| Interactive YOLO toggle | (start over with flag) | TUI option | `Ctrl+Y` | `/yolo` | TUI option |
| Granular allowlist | `/permissions` | `~/.codex/config.toml` | settings | `--allow-all-paths` etc. | `sandbox.json` |
| Persistent config | `.claude/settings.json` | `~/.codex/config.toml` | `~/.gemini/settings.json` | `config.json` | `approvalMode: "unrestricted"` |

---

## Sources

- Anthropic docs (Claude Code)
- OpenAI Codex CLI repo
- GitHub Copilot CLI docs — `/copilot/concepts/agents/copilot-cli/autopilot`
- Cursor CLI docs — `cursor.com/docs/cli/reference/permissions`
- Cursor changelog (2026 releases)
- Google Gemini CLI repo
