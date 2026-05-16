Send a message to the Codex agent on a connected computer via AgentRelay.

## How to run

Detect platform and set paths:
- Windows: relay root = `E:\Programing\AgentRelay`, python = `.venv\Scripts\python.exe`
- Mac/Linux: relay root = `~/Dropbox/AgentRelay`, python = `.venv/bin/python`

The message to send is: $ARGUMENTS

## Steps

1. Run `<python> <relay-root>/agent-send --config <relay-root>/config.yaml --list` to discover peers.

2. Filter out this machine. Find a peer that has `codex-interactive` in its agent list.
   - If multiple peers have Codex, ask: "Which computer? [list]"
   - If no peer has `codex-interactive`, fall back to `codex` (headless).

3. Send: `<python> <relay-root>/agent-send --config <relay-root>/config.yaml <peer> "<message>" --agent codex-interactive`

4. Report result.
