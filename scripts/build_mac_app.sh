#!/bin/bash
# Build AgentRelay.app for macOS (requires: pip install pyinstaller)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt pyinstaller

pyinstaller --noconfirm --windowed --name AgentRelay \
  --osx-bundle-identifier com.agentrelay.app \
  --hidden-import aiohttp \
  --hidden-import zeroconf \
  --hidden-import yaml \
  --hidden-import pyperclip \
  --collect-submodules aiohttp \
  --collect-submodules zeroconf \
  "$ROOT/agentrelay_app.py"

echo ""
echo "Built: $ROOT/dist/AgentRelay.app"
echo "Drag it to Applications, then double-click to run."
