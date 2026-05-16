Send a message to the Cursor agent on a connected computer via AgentRelay.

## How to run

Detect platform and set paths:
- Windows: relay root = `E:\Programing\AgentRelay`, python = `.venv\Scripts\python.exe`
- Mac/Linux: relay root = `~/Dropbox/AgentRelay`, python = `.venv/bin/python`

The message to send is: $ARGUMENTS

## Steps

1. Run `<python> <relay-root>/agent-send --config <relay-root>/config.yaml --list` to discover peers.

2. Filter out this machine. Find a peer that has `cursor-interactive` or `cursor` in its agent list.
   - If multiple peers have Cursor, ask: "Which computer? [list]"
   - If Cursor is not configured on any peer, say so and suggest adding a `cursor-interactive` adapter to that machine's config.yaml.

3. Send: `<python> <relay-root>/agent-send --config <relay-root>/config.yaml <peer> "<message>" --agent cursor-interactive`

4. Report result.
