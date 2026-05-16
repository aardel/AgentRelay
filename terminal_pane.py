"""
terminal_pane.py — Windows WebView2 terminal pane for AgentRelay.

Opens a pywebview window embedding xterm.js that connects to the local
/terminal WebSocket endpoint. Each agent gets its own floating window.

Requires: pywebview >= 4.0  (pip install pywebview)
WebView2 runtime must be installed on the host machine.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

if sys.platform != "win32":
    raise ImportError("terminal_pane is Windows-only; use terminal_pane_unix on Mac/Linux")

try:
    import webview  # pywebview
except ImportError as exc:
    raise ImportError("pywebview is required: pip install pywebview") from exc


# ---------------------------------------------------------------------------
# xterm.js HTML template
# ---------------------------------------------------------------------------
# Bundled inline so the pane works without internet access.
# xterm.js and xterm-addon-fit are loaded from jsDelivr CDN; swap for local
# files if you need air-gapped operation.

_XTERM_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body, #terminal { width: 100%; height: 100%; background: #1e1e1e; }
</style>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/xterm@5/css/xterm.css" />
<script src="https://cdn.jsdelivr.net/npm/xterm@5/lib/xterm.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8/lib/xterm-addon-fit.js"></script>
</head>
<body>
<div id="terminal"></div>
<script>
const AGENT   = "{{AGENT}}";
const PORT    = {{PORT}};
const TOKEN   = "{{TOKEN}}";
const SESSION = "{{SESSION_ID}}";   // "" = create new, uuid = re-attach

const term = new Terminal({
  cursorBlink: true,
  fontSize: 14,
  fontFamily: 'Consolas, "Courier New", monospace',
  theme: { background: "#1e1e1e" },
});
const fitAddon = new FitAddon.FitAddon();
term.loadAddon(fitAddon);
term.open(document.getElementById("terminal"));
fitAddon.fit();

let ws;
let writeToken = null;
let sessionId  = SESSION || null;
let connected  = false;

function connect() {
  ws = new WebSocket(
    `ws://127.0.0.1:${PORT}/terminal?token=${encodeURIComponent(TOKEN)}`);

  ws.onopen = () => {
    connected = true;
    // open or re-attach
    const msg = sessionId
      ? { type: "open", session_id: sessionId }
      : { type: "open", session_id: null, agent: AGENT,
          cols: term.cols, rows: term.rows };
    ws.send(JSON.stringify(msg));
  };

  ws.onmessage = (evt) => {
    const frame = JSON.parse(evt.data);
    switch (frame.type) {
      case "open_ack":
        sessionId  = frame.session_id;
        writeToken = frame.write_token;   // null for read-only viewers
        if (frame.scrollback) {
          const bytes = Uint8Array.from(atob(frame.scrollback),
                                        c => c.charCodeAt(0));
          term.write(bytes);
        }
        break;
      case "data":
        const bytes = Uint8Array.from(atob(frame.data), c => c.charCodeAt(0));
        term.write(bytes);
        break;
      case "resize_sync":
        // Owner drove a resize — update our viewport to match
        term.resize(frame.cols, frame.rows);
        fitAddon.fit();
        break;
      case "closed":
        term.writeln("\\r\\n\\x1b[90m[session ended: " + frame.reason + "]\\x1b[0m");
        connected = false;
        break;
      case "error":
        term.writeln("\\r\\n\\x1b[31m[error " + frame.code + ": " + frame.message + "]\\x1b[0m");
        break;
    }
  };

  ws.onclose = () => {
    connected = false;
    term.writeln("\\r\\n\\x1b[90m[disconnected — retrying in 3s...]\\x1b[0m");
    setTimeout(connect, 3000);
  };

  ws.onerror = () => {
    term.writeln("\\r\\n\\x1b[31m[WebSocket error]\\x1b[0m");
  };
}

// Send keystrokes to PTY (owner only)
term.onData(data => {
  if (!ws || ws.readyState !== WebSocket.OPEN || !writeToken) return;
  const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(data)));
  ws.send(JSON.stringify({ type: "input", session_id: sessionId,
                           write_token: writeToken, data: b64 }));
});

// Owner drives resize; viewers adjust their viewport client-side only
window.addEventListener("resize", () => {
  fitAddon.fit();
  if (writeToken && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "resize", session_id: sessionId,
                             write_token: writeToken,
                             cols: term.cols, rows: term.rows }));
  }
});

connect();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# agent_name → pywebview Window
_open_windows: dict[str, Any] = {}
_webview_started = False
_webview_lock = threading.Lock()


def open_terminal(agent_name: str, port: int, token: str,
                  session_id: str = "") -> None:
    """
    Open (or focus) a WebView2 terminal window for the given agent.

    Safe to call from any thread — pywebview runs on the main thread
    internally; this function spawns it in a daemon thread if not yet started.

    Parameters
    ----------
    agent_name  : adapter name ("claude", "codex", etc.)
    port        : local relay port (default 9876)
    token       : X-Agent-Token value
    session_id  : existing session UUID to re-attach, or "" for new session
    """
    global _webview_started

    with _webview_lock:
        # If window already open, bring it to front
        win = _open_windows.get(agent_name)
        if win is not None:
            try:
                win.show()
                return
            except Exception:
                del _open_windows[agent_name]

    html = (
        _XTERM_HTML
        .replace("{{AGENT}}", agent_name)
        .replace("{{PORT}}", str(port))
        .replace("{{TOKEN}}", token)
        .replace("{{SESSION_ID}}", session_id)
    )

    def _create() -> None:
        global _webview_started
        win = webview.create_window(
            title=f"AgentRelay — {agent_name}",
            html=html,
            width=1000,
            height=600,
            resizable=True,
            on_top=False,
        )
        win.events.closed += lambda: _open_windows.pop(agent_name, None)
        with _webview_lock:
            _open_windows[agent_name] = win

        if not _webview_started:
            _webview_started = True
            webview.start(debug=False)   # blocks until all windows close

    thread = threading.Thread(target=_create, daemon=True, name=f"terminal-{agent_name}")
    thread.start()


def close_terminal(agent_name: str) -> None:
    """Close the terminal window for the given agent if open."""
    win = _open_windows.pop(agent_name, None)
    if win:
        try:
            win.destroy()
        except Exception:
            pass
