Send a message to the Claude agent on a connected computer via AgentRelay.

## How to run

Detect platform and set paths:
- Windows: relay root = `E:\Programing\AgentRelay`, python = `.venv\Scripts\python.exe`
- Mac/Linux: relay root = `~/Dropbox/AgentRelay`, python = `.venv/bin/python`

The message to send is: $ARGUMENTS

## Steps

1. Run `<python> <relay-root>/agent-send --config <relay-root>/config.yaml --list` to discover peers.

2. Filter out this machine. Find a peer that has `claude-interactive` in its agent list.
   - If multiple peers have Claude, ask: "Which computer? [list]"
   - If no peer has `claude-interactive`, fall back to `claude` (headless).

3. Record timestamp before sending (Mac/Linux: `date +%s`).

4. Send: `<python> <relay-root>/agent-send --config <relay-root>/config.yaml <peer> "<message>" --agent claude-interactive`

5. Poll `/inbox` for a reply — up to 36 times × 5s = 3 minutes total. Print a waiting message each poll so the user can see progress:
   ```
   curl -s "http://127.0.0.1:9876/inbox?since=<timestamp>&from=<peer-node-name>"
   ```
   Stop and display the reply as soon as `messages` is non-empty.

6. If a reply arrives: show it here in the conversation, attributed clearly to the peer.
   If no reply in 3 minutes: say so, and remind the user that any later reply will appear in the GUI "Messages received" panel.
