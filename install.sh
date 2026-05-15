#!/usr/bin/env bash
# install.sh - set up agentrelay on this machine
#
# Usage:
#   ./install.sh              # install to /usr/local with a dedicated venv
#   PREFIX=$HOME/.local ./install.sh   # user-only install
#   ./install.sh --service    # also install + start the OS service

set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
VENV="$PREFIX/lib/agentrelay"
BIN="$PREFIX/bin"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SERVICE=0

for arg in "$@"; do
    case "$arg" in
        --service) INSTALL_SERVICE=1 ;;
        *) echo "unknown arg: $arg" >&2; exit 1 ;;
    esac
done

SUDO=""
if [ ! -w "$PREFIX" ]; then
    SUDO="sudo"
fi

echo "==> creating venv at $VENV"
$SUDO mkdir -p "$VENV" "$BIN"
$SUDO python3 -m venv "$VENV"
$SUDO "$VENV/bin/pip" install --quiet --upgrade pip
$SUDO "$VENV/bin/pip" install --quiet -r "$SRC_DIR/requirements.txt"

echo "==> installing files"
$SUDO install -m 0755 "$SRC_DIR/agentrelay.py"     "$VENV/agentrelay.py"
$SUDO install -m 0755 "$SRC_DIR/agent-send"       "$VENV/agent-send"
$SUDO install -m 0755 "$SRC_DIR/agent-talk"      "$VENV/agent-talk"
$SUDO install -m 0644 "$SRC_DIR/talk.py"         "$VENV/talk.py"
$SUDO install -m 0644 "$SRC_DIR/pairing.py"      "$VENV/pairing.py"
$SUDO install -m 0644 "$SRC_DIR/config_io.py"   "$VENV/config_io.py"
$SUDO install -m 0755 "$SRC_DIR/agent-forward"  "$VENV/agent-forward"
$SUDO install -m 0755 "$SRC_DIR/agentrelay_gui.py" "$VENV/agentrelay_gui.py"
$SUDO install -m 0755 "$SRC_DIR/agentrelay_app.py"  "$VENV/agentrelay_app.py"
$SUDO install -m 0644 "$SRC_DIR/relay_client.py"   "$VENV/relay_client.py"
$SUDO cp -R "$SRC_DIR/gui" "$VENV/gui"

# Wrapper scripts that invoke the venv's python
$SUDO tee "$BIN/agentrelay" >/dev/null <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$VENV/agentrelay.py" "\$@"
EOF
$SUDO chmod 0755 "$BIN/agentrelay"

$SUDO tee "$BIN/agent-send" >/dev/null <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$VENV/agent-send" "\$@"
EOF
$SUDO chmod 0755 "$BIN/agent-send"

$SUDO tee "$BIN/agent-talk" >/dev/null <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$VENV/agent-talk" "\$@"
EOF
$SUDO chmod 0755 "$BIN/agent-talk"

$SUDO tee "$BIN/agent-forward" >/dev/null <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$VENV/agent-forward" "\$@"
EOF
$SUDO chmod 0755 "$BIN/agent-forward"

$SUDO tee "$BIN/agentrelay-gui" >/dev/null <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$VENV/agentrelay_gui.py" "\$@"
EOF
$SUDO chmod 0755 "$BIN/agentrelay-gui"

echo "==> generating config (if missing)"
"$BIN/agentrelay" --init || true

if [ "$INSTALL_SERVICE" = "1" ]; then
    case "$(uname -s)" in
        Darwin)
            PLIST_SRC="$SRC_DIR/service/local.agentrelay.plist"
            if [ ! -f "$PLIST_SRC" ]; then
                PLIST_SRC="$SRC_DIR/local.agentrelay.plist"
            fi
            DEST="$HOME/Library/LaunchAgents/local.agentrelay.plist"
            mkdir -p "$(dirname "$DEST")"
            cp "$PLIST_SRC" "$DEST"
            # Patch ExecPath to match $BIN
            sed -i '' "s|/usr/local/bin/agentrelay|$BIN/agentrelay|g" "$DEST"
            launchctl unload "$DEST" 2>/dev/null || true
            launchctl load "$DEST"
            echo "==> launchd service loaded: local.agentrelay"
            echo "    logs: /tmp/agentrelay.{out,err}.log"
            ;;
        Linux)
            SERVICE_SRC="$SRC_DIR/service/agentrelay.service"
            if [ ! -f "$SERVICE_SRC" ]; then
                SERVICE_SRC="$SRC_DIR/agentrelay.service"
            fi
            DEST="$HOME/.config/systemd/user/agentrelay.service"
            mkdir -p "$(dirname "$DEST")"
            mkdir -p "$HOME/.local/state"
            cp "$SERVICE_SRC" "$DEST"
            sed -i "s|/usr/local/bin/agentrelay|$BIN/agentrelay|g" "$DEST"
            systemctl --user daemon-reload
            systemctl --user enable --now agentrelay.service
            echo "==> systemd user service enabled: agentrelay"
            echo "    status: systemctl --user status agentrelay"
            ;;
        *)
            echo "==> --service not supported on $(uname -s); start manually:"
            echo "    $BIN/agentrelay"
            ;;
    esac
fi

echo
echo "Done."
echo "  agentrelay   -> $BIN/agentrelay"
echo "  agent-send   -> $BIN/agent-send"
echo "  config       -> ~/.config/agentrelay/config.yaml"
echo
echo "Next: copy the token from this machine's config into the same"
echo "field in every other machine's config, then start agentrelay there."
