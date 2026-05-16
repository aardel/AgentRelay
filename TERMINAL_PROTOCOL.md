# AgentRelay Terminal Protocol

Defines the `PTYSession` interface and `/terminal` WebSocket protocol for
embedding live agent terminals in the AgentRelay GUI.

**Status:** Design spec — agreed between WINPC Claude and Mac Claude.

---

## PTYSession

Each agent process gets one `PTYSession`. The session survives subscriber churn
(viewers connecting/disconnecting) and can be re-attached after a network blip.

```python
@dataclass
class PTYSession:
    session_id: str        # stable UUID — survives subscriber churn
    agent_name: str        # "claude", "codex", "gemini", etc.
    node: str              # owning node name
    cols: int = 220
    rows: int = 50

    # Internal
    _proc: Any             # pty handle (pywinpty on Windows, pty module on Mac/Linux)
    _subscribers: set      # active WebSocket connections (read-only viewers)
    _write_token: str      # capability token — required to send input
    _output_buf: deque     # rolling scrollback buffer, capped (e.g. 10 000 lines)

    async def start(self, cmd: list[str]) -> None: ...
    async def stop(self) -> None: ...

    async def write(self, data: str, token: str) -> None:
        # Raises PermissionError if token does not match _write_token
        ...

    async def resize(self, cols: int, rows: int) -> None:
        # Updates PTY dimensions and broadcasts resize_sync to all subscribers
        ...

    async def subscribe(self, ws: WebSocket) -> None:
        # Sends scrollback snapshot then streams live output
        ...

    async def unsubscribe(self, ws: WebSocket) -> None: ...

    def grant_write(self) -> str:
        # Generates and returns a new _write_token (owner only)
        ...
```

**Platform backends:**
- Windows: [`pywinpty`](https://github.com/andfoy/pywinpty) (ConPTY, used by Jupyter)
- Mac/Linux: stdlib `pty` module

**Frontend:** [`xterm.js`](https://xtermjs.org/) embedded via WebView2 (Windows) or
WKWebView/CEF (Mac/Linux). PTY output is passed as raw VT bytes — no relay-side
parsing needed.

---

## `/terminal` WebSocket Protocol

All frames are UTF-8 JSON. Directions: **C→S** (client to server), **S→C** (server to client).

### `open` — C→S

Start a new session or re-attach to an existing one.

```json
{
  "type": "open",
  "session_id": "<uuid | null>",
  "agent": "claude",
  "cols": 220,
  "rows": 50
}
```

- `session_id: null` — create a new session
- `session_id: "<uuid>"` — attach to existing session (re-attach after disconnect)
- `agent` — optional when re-attaching to an existing `session_id`; ignored if provided

---

### `open_ack` — S→C

```json
{
  "type": "open_ack",
  "session_id": "<uuid>",
  "write_token": "<token | null>",
  "scrollback": "<base64 vt bytes>"
}
```

- `write_token: null` — client is a read-only viewer (remote peer)
- `scrollback` — base64-encoded VT scrollback buffer for catch-up on attach

---

### `data` — S→C

Live PTY output, broadcast to all subscribers.

```json
{
  "type": "data",
  "session_id": "<uuid>",
  "data": "<base64 vt bytes>"
}
```

PTY output is forwarded as raw VT bytes. xterm.js consumes these directly.

---

### `input` — C→S

Send keystrokes to the PTY. Requires `write_token`.

```json
{
  "type": "input",
  "session_id": "<uuid>",
  "write_token": "<token>",
  "data": "<base64 encoded keystrokes>"
}
```

---

### `resize` — C→S

Resize the PTY. Requires `write_token` (owner only).

```json
{
  "type": "resize",
  "session_id": "<uuid>",
  "write_token": "<token>",
  "cols": 220,
  "rows": 50
}
```

Read-only viewers do **not** send `resize`. They adjust their xterm.js
viewport client-side only.

---

### `resize_sync` — S→C

Broadcast to all subscribers when the owner resizes, so every xterm.js
instance stays at the authoritative dimensions and avoids line-wrap desync.

```json
{
  "type": "resize_sync",
  "session_id": "<uuid>",
  "cols": 220,
  "rows": 50
}
```

---

### `close` — C→S

Terminate the session and its PTY process. Requires `write_token` (owner only).
Read-only viewers disconnect silently without sending `close`.

```json
{
  "type": "close",
  "session_id": "<uuid>",
  "write_token": "<token>"
}
```

---

### `closed` — S→C

Broadcast to all subscribers when a session ends.

```json
{
  "type": "closed",
  "session_id": "<uuid>",
  "reason": "owner_closed | process_exited | error"
}
```

---

### `error` — S→C

```json
{
  "type": "error",
  "session_id": "<uuid>",
  "code": "unauthorized | session_not_found | pty_error",
  "message": "..."
}
```

---

## Design decisions

| Decision | Rationale |
|---|---|
| Stable `session_id` | Viewers can re-attach after a network blip; PTY survives like a tmux session |
| `write_token` capability | Owner grants write access explicitly; remote viewers are read-only by default |
| Raw VT bytes (base64) | No relay-side terminal parsing; xterm.js handles all VT100/256color/true-color |
| `resize_sync` broadcast | Keeps all xterm.js viewports at consistent dimensions; prevents line-wrap desync |
| Viewers resize client-side only | Read-only viewers adjust their local xterm.js viewport; never send `resize` to server |
| `agent` optional on re-attach | `session_id` uniquely identifies the session; `agent` is informational only at that point |
| Remote panes read-only by default | Security posture; write access requires the owning daemon to issue a capability token |
