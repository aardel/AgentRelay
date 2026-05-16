/**
 * Embedded xterm.js panes — connects to AgentRelay /terminal WebSocket.
 * Token is passed as a query parameter (browser WebSocket cannot set headers).
 */
(function (global) {
  const tabsEl = () => document.getElementById("terminal-tabs");
  const panelsEl = () => document.getElementById("terminal-panels");

  let tabCounter = 0;
  const tabs = new Map();
  /** @type {{ agent: string, prompt: string, waitSeconds: number }[]} */
  const pendingDeliveries = [];

  function sendInput(tab, text) {
    if (!tab || !tab.writeToken || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    const bytes = new TextEncoder().encode(text);
    tab.ws.send(JSON.stringify({
      type: "input",
      session_id: tab.sessionId,
      write_token: tab.writeToken,
      data: bytesToB64(bytes),
    }));
    return true;
  }

  function injectPrompt(tab, prompt, waitSeconds) {
    if (!sendInput(tab, prompt)) return false;
    window.setTimeout(() => sendInput(tab, "\r"), Math.max(1000, waitSeconds * 1000));
    return true;
  }

  function flushPendingForAgent(agent) {
    const rest = [];
    for (const item of pendingDeliveries) {
      if (item.agent !== agent) {
        rest.push(item);
        continue;
      }
      let delivered = false;
      tabs.forEach((tab) => {
        if (tab.agent === agent && tab.sessionId && tab.writeToken) {
          delivered = injectPrompt(tab, item.prompt, item.waitSeconds) || delivered;
        }
      });
      if (!delivered) rest.push(item);
    }
    pendingDeliveries.length = 0;
    pendingDeliveries.push(...rest);
  }

  /**
   * Deliver a relay message into an open agent terminal (or queue until open_ack).
   * @returns {boolean} true if injected or queued for a pending session
   */
  function deliverToAgent(agent, port, token, prompt, waitSeconds) {
    waitSeconds = waitSeconds || 5;
    let delivered = false;
    tabs.forEach((tab) => {
      if (tab.agent === agent && tab.sessionId && tab.writeToken) {
        delivered = injectPrompt(tab, prompt, waitSeconds) || delivered;
      }
    });
    if (delivered) return true;

    const hasTab = [...tabs.values()].some((t) => t.agent === agent);
    if (!hasTab) {
      openTerminal(agent, port, token, { reuse: true, injectSnippet: false });
    }
    pendingDeliveries.push({ agent, prompt, waitSeconds });
    return true;
  }

  function wsUrl(port, token) {
    return `ws://127.0.0.1:${port}/terminal?token=${encodeURIComponent(token)}`;
  }

  function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function bytesToB64(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
  }

  function activateTab(id) {
    tabs.forEach((tab, key) => {
      tab.wrap.classList.toggle("active", key === id);
      tab.panel.classList.toggle("active", key === id);
      if (key === id && tab.fitAddon) {
        setTimeout(() => tab.fitAddon.fit(), 50);
      }
    });
  }

  function closeTab(id) {
    const tab = tabs.get(id);
    if (!tab) return;
    if (tab.ws && tab.ws.readyState === WebSocket.OPEN) {
      tab.ws.close();
    }
    tab.term.dispose();
    tab.wrap.remove();
    tab.panel.remove();
    tabs.delete(id);
    const remaining = [...tabs.keys()];
    if (remaining.length) activateTab(remaining[remaining.length - 1]);
  }

  /**
   * @param {string} agent
   * @param {number} port
   * @param {string} token
   * @param {{ sessionId?: string, injectSnippet?: boolean, reuse?: boolean, yolo?: boolean, profile?: string }} options
   */
  function openTerminal(agent, port, token, options) {
    options = options || {};
    const sessionId = options.sessionId || null;
    const injectSnippet = Boolean(options.injectSnippet);
    const reuse = options.reuse !== false;
    const yolo = Boolean(options.yolo);
    const profile = options.profile || null;

    if (!global.Terminal || !global.FitAddon) {
      throw new Error("xterm.js not loaded");
    }
    const id = `t${++tabCounter}`;

    const wrap = document.createElement("div");
    wrap.className = "terminal-tab";
    wrap.setAttribute("role", "tab");

    const label = document.createElement("button");
    label.type = "button";
    label.className = "terminal-tab-label";
    label.textContent = agent;
    label.title = `Show ${agent}`;
    label.addEventListener("click", () => activateTab(id));

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "terminal-tab-close";
    closeBtn.setAttribute("aria-label", `Close ${agent} tab`);
    closeBtn.innerHTML = "&times;";
    closeBtn.title = "Close tab";
    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      closeTab(id);
    });

    wrap.appendChild(label);
    wrap.appendChild(closeBtn);

    const panel = document.createElement("div");
    panel.className = "terminal-panel";
    panel.id = `panel-${id}`;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: { background: "#1e1e1e" },
    });
    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(panel);

    tabs.set(id, { wrap, panel, term, fitAddon, ws: null, agent, sessionId: null });
    tabsEl().appendChild(wrap);
    panelsEl().appendChild(panel);
    activateTab(id);
    fitAddon.fit();

    const ws = new WebSocket(wsUrl(port, token));
    tabs.get(id).ws = ws;

    ws.onopen = () => {
      const msg = sessionId
        ? { type: "open", session_id: sessionId }
        : {
            type: "open",
            session_id: null,
            agent,
            cols: term.cols,
            rows: term.rows,
            inject_snippet: injectSnippet,
            reuse,
            yolo,
            profile,
          };
      ws.send(JSON.stringify(msg));
    };

    ws.onmessage = (ev) => {
      let frame;
      try {
        frame = JSON.parse(ev.data);
      } catch {
        return;
      }
      const tab = tabs.get(id);
      if (!tab) return;
      switch (frame.type) {
        case "open_ack":
          tab.sessionId = frame.session_id;
          tab.writeToken = frame.write_token;
          term.clear();
          if (frame.scrollback) term.write(b64ToBytes(frame.scrollback));
          fitAddon.fit();
          if (typeof options.onOpen === "function") options.onOpen(frame);
          flushPendingForAgent(tab.agent);
          break;
        case "data":
          if (frame.data) term.write(b64ToBytes(frame.data));
          break;
        case "resize_sync":
          break;
        case "closed":
          term.writeln(`\r\n\x1b[90m[session ended: ${frame.reason}]\x1b[0m`);
          break;
        case "error":
          term.writeln(`\r\n\x1b[31m[${frame.code}] ${frame.message}\x1b[0m`);
          break;
        default:
          break;
      }
    };

    ws.onclose = () => {
      term.writeln("\r\n\x1b[90m[disconnected]\x1b[0m");
    };

    term.onData((data) => {
      const tab = tabs.get(id);
      if (!tab || !tab.writeToken || ws.readyState !== WebSocket.OPEN) return;
      const bytes = new TextEncoder().encode(data);
      ws.send(JSON.stringify({
        type: "input",
        session_id: tab.sessionId,
        write_token: tab.writeToken,
        data: bytesToB64(bytes),
      }));
    });

    term.onResize(({ cols, rows }) => {
      const tab = tabs.get(id);
      if (!tab || !tab.writeToken || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({
        type: "resize",
        session_id: tab.sessionId,
        write_token: tab.writeToken,
        cols,
        rows,
      }));
    });

    window.addEventListener("resize", () => {
      if (tabs.get(id)?.panel.classList.contains("active")) {
        fitAddon.fit();
      }
    });

    return id;
  }

  function getActiveSelection() {
    let selection = "";
    tabs.forEach((tab) => {
      if (tab.panel.classList.contains("active")) {
        selection = tab.term.getSelection();
      }
    });
    return selection;
  }

  function clearActiveTerminal() {
    tabs.forEach((tab) => {
      if (tab.panel.classList.contains("active")) {
        tab.term.clear();
      }
    });
  }

  function sendToActiveTerminal(text) {
    let sent = false;
    tabs.forEach((tab) => {
      if (tab.panel.classList.contains("active")) {
        sent = sendInput(tab, text) || sent;
      }
    });
    return sent;
  }

  global.AgentRelayTerminals = {
    openTerminal,
    closeTab,
    deliverToAgent,
    getActiveSelection,
    clearActiveTerminal,
    sendToActiveTerminal,
  };
})(window);
