#!/bin/bash
# Double-click this file on Mac to open AgentRelay (after running install.sh once).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  osascript -e 'display alert "AgentRelay" message "Run ./install.sh in this folder first."'
  exit 1
fi

PY="$DIR/.venv/bin/python"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Start background service if not already running
if ! curl -sf "http://127.0.0.1:9876/health" >/dev/null 2>&1; then
  "$PY" "$DIR/agentrelay.py" --config "$HOME/.config/agentrelay/config.yaml" &
  sleep 1
fi

exec "$PY" "$DIR/agentrelay_app.py"
