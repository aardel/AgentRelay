Send a message to an agent on a connected computer via AgentRelay.

## How to run

Detect platform and set paths:
- Windows: relay root = `E:\Programing\AgentRelay`, python = `.venv\Scripts\python.exe`, agent-send = `agent-send`
- Mac/Linux: relay root = `~/Dropbox/AgentRelay`, python = `.venv/bin/python`, agent-send = `agent-send`

The message to send is: $ARGUMENTS

## Steps

1. Run `<python> <relay-root>/agent-send --config <relay-root>/config.yaml --list` to get available peers and their agents.

2. Parse the peer list. Filter out this machine (marked with `*`).

3. Determine target peer and agent from $ARGUMENTS if specified (e.g. "fix login bug --to WINPC --agent codex"). Otherwise:
   - If only one peer exists, use it.
   - If multiple peers exist, ask: "Which computer should I send this to? [list peers]"
   - If the chosen peer has multiple interactive agents, ask: "Which agent on [peer]? [list agents]"
   - Prefer `*-interactive` adapters over headless ones for visible delivery.

4. Send: `<python> <relay-root>/agent-send --config <relay-root>/config.yaml <peer> "<message>" --agent <agent>`

5. Report back what was sent, to where, and whether it succeeded.
