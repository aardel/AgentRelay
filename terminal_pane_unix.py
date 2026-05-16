"""
terminal_pane_unix.py — Mac/Linux WebKit terminal pane for AgentRelay.

Opens a pywebview window embedding xterm.js that connects to the local
/terminal WebSocket endpoint. Each agent gets its own floating window.

The window runs in a separate process to avoid conflict with tkinter's
main-thread run loop — AppKit and tkinter both require the main thread,
so isolation via multiprocessing is the cleanest solution.

Requires: pywebview >= 4.0  (pip install pywebview)
  macOS : WebKit is built-in — no extra runtime needed.
  Linux : pip install pywebview[gtk]  or  pip install pywebview[qt]
"""
from __future__ import annotations

import multiprocessing
import sys
import threading

if sys.platform == "win32":
    raise ImportError("terminal_pane_unix is Mac/Linux only; use terminal_pane on Windows")


# ---------------------------------------------------------------------------
# xterm.js HTML template — identical to the Windows pane for consistent UX
# ---------------------------------------------------------------------------

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
  fontFamily: 'Menlo, "Courier New", monospace',
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
  ws = new WebSocket(`ws://127.0.0.1:${PORT}/terminal`,
                     [], { headers: { "X-Agent-Token": TOKEN } });

  ws.onopen = () => {
    connected = true;
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
# Webview subprocess entry point
# ---------------------------------------------------------------------------

def _run_webview(agent_name: str, html: str) -> None:
    """Runs in a dedicated process — owns the main thread for AppKit/GTK."""
    try:
        import webview
    except ImportError:
        return
    webview.create_window(
        title=f"AgentRelay — {agent_name}",
        html=html,
        width=1000,
        height=600,
        resizable=True,
        on_top=False,
    )
    webview.start()


# ---------------------------------------------------------------------------
# Public API (matches terminal_pane.py on Windows)
# ---------------------------------------------------------------------------

_open_procs: dict[str, multiprocessing.Process] = {}
_lock = threading.Lock()


def open_terminal(agent_name: str, port: int, token: str,
                  session_id: str = "") -> None:
    """
    Open (or no-op if already running) a WebKit terminal for the given agent.

    Safe to call from any thread. Each call spawns an isolated process so
    AppKit's main-thread requirement doesn't conflict with tkinter's run loop.

    Parameters
    ----------
    agent_name  : adapter name ("claude", "codex", etc.)
    port        : local relay port (default 9876)
    token       : X-Agent-Token value
    session_id  : existing session UUID to re-attach, or "" for new session
    """
    with _lock:
        proc = _open_procs.get(agent_name)
        if proc is not None and proc.is_alive():
            return  # window already open
        _open_procs.pop(agent_name, None)

    html = (
        _XTERM_HTML
        .replace("{{AGENT}}", agent_name)
        .replace("{{PORT}}", str(port))
        .replace("{{TOKEN}}", token)
        .replace("{{SESSION_ID}}", session_id)
    )

    proc = multiprocessing.Process(
        target=_run_webview,
        args=(agent_name, html),
        daemon=True,
        name=f"terminal-{agent_name}",
    )
    proc.start()
    with _lock:
        _open_procs[agent_name] = proc


def close_terminal(agent_name: str) -> None:
    """Terminate the terminal window for the given agent if running."""
    with _lock:
        proc = _open_procs.pop(agent_name, None)
    if proc and proc.is_alive():
        proc.terminate()
