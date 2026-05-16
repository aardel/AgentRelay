#!/bin/bash
# Double-click from Finder (or Desktop) to start AgentRelay.
set -euo pipefail

# Resolve project root (Desktop launcher sets AGENTRELAY_ROOT)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${AGENTRELAY_ROOT:-}" ] && [ -f "$AGENTRELAY_ROOT/agentrelay.py" ]; then
  ROOT="$AGENTRELAY_ROOT"
elif [ -f "$SCRIPT_DIR/../agentrelay.py" ]; then
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [ -f "$HOME/Library/CloudStorage/Dropbox/AgentRelay/agentrelay.py" ]; then
  ROOT="$HOME/Library/CloudStorage/Dropbox/AgentRelay"
else
  osascript -e 'display alert "AgentRelay not found" message "Set AGENTRELAY_ROOT to your clone path."'
  exit 1
fi

cd "$ROOT"
CONFIG="${AGENTRELAY_CONFIG:-$ROOT/config.yaml}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f "$CONFIG" ]; then
  python agentrelay.py --init --config "$CONFIG"
fi

# Single GUI instance — second click focuses existing UI in browser
if [ -f /tmp/agentrelay-gui.pid ] && kill -0 "$(cat /tmp/agentrelay-gui.pid)" 2>/dev/null; then
  PORT=$(python -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['port'])")
  TOKEN=$(python -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['token'])")
  open "http://127.0.0.1:${PORT}/?token=${TOKEN}&port=${PORT}"
  exit 0
fi

exec python agentrelay_gui.py --config "$CONFIG"
