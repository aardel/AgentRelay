#!/bin/bash
# Copy AgentRelay.command to the Desktop (macOS).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/Desktop/AgentRelay.command"

cat > "$DEST" <<EOF
#!/bin/bash
export AGENTRELAY_ROOT="$ROOT"
export AGENTRELAY_CONFIG="\${AGENTRELAY_CONFIG:-$ROOT/config.yaml}"
exec "\$AGENTRELAY_ROOT/scripts/Launch-AgentRelay.command"
EOF
chmod +x "$DEST"
chmod +x "$ROOT/scripts/Launch-AgentRelay.command"

echo "Installed: $DEST"
echo "Double-click AgentRelay on your Desktop to start."
