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

3. Record the current timestamp (seconds since epoch) before sending — you'll use it to filter inbox replies.
   On Mac/Linux: `date +%s`
   On Windows: `[int][double]::Parse((Get-Date -UFormat %s))`

4. Send: `<python> <relay-root>/agent-send --config <relay-root>/config.yaml <peer> "<message>" --agent claude-interactive`

5. Poll the local relay inbox for a reply from that peer. Repeat up to 12 times with 5-second waits (60s total):
   `curl -s "http://127.0.0.1:9876/inbox?since=<timestamp>&from=<peer-node-name>"`
   Stop as soon as `messages` is non-empty.

6. Display the reply message(s) clearly, attributed to the peer. If no reply arrives within 60s, say so.
