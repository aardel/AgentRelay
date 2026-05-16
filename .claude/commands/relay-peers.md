List all connected computers and their available agents via AgentRelay.

## How to run

Detect platform and set paths:
- Windows: relay root = `E:\Programing\AgentRelay`, python = `.venv\Scripts\python.exe`
- Mac/Linux: relay root = `~/Dropbox/AgentRelay`, python = `.venv/bin/python`

Run: `<python> <relay-root>/agent-send --config <relay-root>/config.yaml --list`

Then show the results clearly, marking which machine is the current one (`*`) and listing the agents configured on each peer from the AgentRelay config. Suggest the right `/relay-*` skill to use for each agent.
