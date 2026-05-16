# AgentRelay Implementation Summary

This document summarizes what has been built so far and how the pieces fit
together.

## What Was Built

AgentRelay is now a cross-platform desktop and daemon app for routing work
between AI agents on trusted machines.

Completed work includes:

- Local HTTP/WebSocket daemon with token authentication.
- LAN peer discovery through mDNS.
- Pairing and trusted peer tracking.
- Web-based desktop UI loaded through pywebview.
- Legacy Tkinter UI retained as a fallback.
- Embedded terminal tabs using xterm.js and PTY backends.
- Local PTY support on macOS/Linux and Windows PTY support through pywinpty.
- Agent launch flow for configured Claude, Codex, Gemini, Cursor, and custom
  adapters.
- AgentRelay instruction injection into launched terminal sessions.
- YOLO/full-auto launch mode that adds each CLI's skip-permission flags.
- Skills installer for Claude Code, Codex, and Gemini slash commands.
- Message forwarding with local and remote agent targeting.
- Global broadcast messages sent to all configured agents.
- Incoming message inbox in the GUI.
- Relay delivery into open embedded terminals, with queued delivery while a
  terminal is opening.
- Windows-specific delivery support for interactive console agents.
- Single-instance locks for the daemon and GUI.
- macOS and Windows desktop launcher scripts.
- Installer updates for macOS/Linux and Windows.
- Focused tests for API routes, broadcasts, delivery, skills, launch flags,
  GUI paths, launch arguments, and Windows launcher behavior.

## Current User Flow

1. Install AgentRelay on each trusted machine.
2. Start the desktop app with the Desktop launcher or `agentrelay-gui`.
3. Pair machines or use a shared token in `config.yaml`.
4. Install relay skills into the desired AI CLI.
5. Launch an agent in an embedded terminal.
6. Send work with `agent-send`, `agent-forward`, or installed slash commands.
7. Review incoming work in the Messages view or in the target terminal.

## Main Components

| Path | Purpose |
| --- | --- |
| `agentrelay.py` | Main daemon, API routes, peer discovery, dispatch, terminal WebSocket handling. |
| `agentrelay_gui.py` | Legacy Tkinter desktop app fallback. |
| `agentrelay_web.py` | pywebview desktop shell for the local web UI. |
| `relay_client.py` | Shared desktop/client helpers for relay control, skills, launch, and delivery. |
| `pty_session.py` | Cross-platform PTY session registry and terminal session abstraction. |
| `pty_unix.py` | macOS/Linux PTY backend. |
| `pty_windows.py` | Windows PTY backend. |
| `gui/index.html` | Web UI markup. |
| `gui/app.js` | Web UI API, pairing, send, skills, inbox, and launch logic. |
| `gui/terminals.js` | xterm.js terminal tabs and WebSocket protocol client. |
| `yolo_flags.py` | Agent-specific full-auto launch flag mapping. |
| `scripts/` | Desktop launchers and build/install helpers. |
| `tests/` | Regression tests for API, launch, delivery, and platform behavior. |

## Key Behaviors

### Terminal Launch

The GUI opens a `/terminal` WebSocket to the local daemon. The daemon creates a
PTY session for the selected adapter and streams raw terminal data to xterm.js.
The browser receives a write token for local sessions and uses it to send input,
resize events, and close requests.

### Relay Delivery

Incoming dispatches are stored in the local inbox. Interactive messages can be
delivered to an embedded terminal for the target agent. If a matching terminal
is not open yet, the frontend opens one and queues the prompt until the session
acknowledges.

### Global Broadcast

Global broadcast mode wraps the message with a clear broadcast header and sends
it to all available configured agents. Broadcasts are also covered by API tests.

### YOLO Mode

YOLO mode is an explicit UI checkbox. When enabled, launch commands include
agent-specific skip-permission flags such as Claude's dangerous skip flag or
Codex's approval/sandbox bypass flags. This should only be used in trusted
projects.

## Verification

Existing test coverage includes:

- GUI API routes.
- Skills API and generated slash commands.
- YOLO flag generation.
- Interactive launch argument construction.
- Agent send CLI behavior.
- Broadcast API behavior.
- Delivery to local and peer agents.
- Windows interactive delivery behavior.
- Windows launcher script behavior.
- PID lock behavior.

Run the test suite with:

```bash
pytest
```

## Known Remaining Work

- Test real Windows to macOS and macOS to Windows interactive delivery end to
  end on two physical machines.
- Retire the Tkinter UI once the web UI has complete parity.
- Add durable logs and session history.
- Add reusable permission profiles beyond the current YOLO checkbox.
- Add remote read-only terminal attach for peer machines.
- Ensure packaged builds include every GUI asset and PTY backend dependency.

## Related Docs

- [README](../README.md)
- [Task list](TASKS.md)
- [Terminal protocol](../TERMINAL_PROTOCOL.md)
- [YOLO flags reference](ai-cli-agents-yolo-flags.md)
- [Feature roadmap](feature-roadmap.md)
