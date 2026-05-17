/**
 * Embedded xterm.js panes — connects to AgentRelay /terminal WebSocket.
 * Token is passed as a query parameter (browser WebSocket cannot set headers).
 */
(function (global) {
  const tabsEl = () => document.getElementById("terminal-tabs");
  const panelsEl = () => document.getElementById("terminal-panels");

  let tabCounter = 0;
  const tabs = new Map();
  /** @type {{ agent: string, prompt: string, waitSeconds: number, workMeta?: { kind: string, id: string } }[]} */
  const pendingDeliveries = [];

  function bindWorkSession(sessionId, workMeta, port, token) {
    if (!workMeta || !sessionId || !port || !token) return;
    fetch(`http://127.0.0.1:${port}/api/work-queue/bind`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Agent-Token": token,
      },
      body: JSON.stringify({
        session_id: sessionId,
        kind: workMeta.kind,
        id: workMeta.id,
      }),
    }).catch(() => {});
  }

  // Multi-pane layout state
  let currentLayout = "1";
  const gridPanelIds = []; // tab IDs visible in grid, in display order

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

  function flushPendingForAgent(agent, port, token) {
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
          if (delivered && item.workMeta) {
            bindWorkSession(tab.sessionId, item.workMeta, port, token);
          }
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
  function deliverToAgent(agent, port, token, prompt, waitSeconds, workMeta) {
    waitSeconds = waitSeconds || 5;
    let delivered = false;
    tabs.forEach((tab) => {
      if (tab.agent === agent && tab.sessionId && tab.writeToken) {
        delivered = injectPrompt(tab, prompt, waitSeconds) || delivered;
        if (delivered && workMeta) {
          bindWorkSession(tab.sessionId, workMeta, port, token);
        }
      }
    });
    if (delivered) return true;

    const hasTab = [...tabs.values()].some((t) => t.agent === agent);
    if (!hasTab) {
      openTerminal(agent, port, token, { reuse: true, injectSnippet: false });
    }
    pendingDeliveries.push({ agent, prompt, waitSeconds, workMeta });
    return true;
  }

  function wsUrl(host, port, token) {
    return `ws://${host}:${port}/terminal?token=${encodeURIComponent(token)}`;
  }

  function httpUrl(host, port, path, token) {
    return `http://${host}:${port}${path}?token=${encodeURIComponent(token)}`;
  }

  const XTERM_THEME = {
    background: "#1e1e1e",
    foreground: "#d4d4d4",
    cursor: "#d4d4d4",
    black: "#1e1e1e",
    red: "#f44747",
    green: "#6a9955",
    yellow: "#dcdcaa",
    blue: "#569cd6",
    magenta: "#c586c0",
    cyan: "#4ec9b0",
    white: "#d4d4d4",
    brightBlack: "#808080",
    brightRed: "#f44747",
    brightGreen: "#6a9955",
    brightYellow: "#dcdcaa",
    brightBlue: "#569cd6",
    brightMagenta: "#c586c0",
    brightCyan: "#4ec9b0",
    brightWhite: "#ffffff",
  };

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
    if (currentLayout !== "1") {
      // Grid mode: make this pane focused; rotate it to front of gridPanelIds
      const maxPanes = currentLayout === "4" ? 4 : 2;
      const idx = gridPanelIds.indexOf(id);
      if (idx !== -1) gridPanelIds.splice(idx, 1);
      gridPanelIds.unshift(id);
      // Fill remaining slots with existing tabs (in creation order)
      [...tabs.keys()].forEach(k => {
        if (!gridPanelIds.includes(k) && gridPanelIds.length < maxPanes) gridPanelIds.push(k);
      });
      tabs.forEach((tab, key) => {
        const pos = gridPanelIds.indexOf(key);
        const visible = pos !== -1 && pos < maxPanes;
        tab.panel.style.order = visible ? pos : 99;
        tab.panel.classList.toggle("grid-visible", visible);
        tab.panel.classList.toggle("grid-focused", key === id);
        tab.wrap.classList.toggle("active", key === id);
        if (visible) setTimeout(() => tab.fitAddon && tab.fitAddon.fit(), 50);
      });
      return;
    }
    // Single-pane mode
    tabs.forEach((tab, key) => {
      tab.wrap.classList.toggle("active", key === id);
      tab.panel.classList.toggle("active", key === id);
      if (key === id && tab.fitAddon) setTimeout(() => tab.fitAddon.fit(), 50);
    });
  }

  function setLayout(layout) {
    currentLayout = layout;
    const panels = panelsEl();
    panels.className = "terminal-panels" + (layout !== "1" ? " layout-" + layout : "");
    document.querySelectorAll(".terminal-layout-btn").forEach(b =>
      b.classList.toggle("active", b.dataset.layout === layout));

    if (layout === "1") {
      gridPanelIds.length = 0;
      tabs.forEach(tab => {
        tab.panel.classList.remove("grid-visible", "grid-focused");
        tab.panel.style.order = "";
      });
      const ids = [...tabs.keys()];
      if (ids.length) activateTab(ids[ids.length - 1]);
    } else {
      // Seed grid with up to N most recently opened tabs
      const maxPanes = layout === "4" ? 4 : 2;
      gridPanelIds.length = 0;
      [...tabs.keys()].slice(-maxPanes).reverse().forEach(id => gridPanelIds.push(id));
      tabs.forEach((tab, id) => {
        const pos = gridPanelIds.indexOf(id);
        const visible = pos !== -1;
        tab.panel.classList.remove("active");
        tab.panel.style.order = visible ? pos : 99;
        tab.panel.classList.toggle("grid-visible", visible);
        tab.panel.classList.toggle("grid-focused", pos === 0);
        tab.wrap.classList.toggle("active", pos === 0);
        if (visible) setTimeout(() => tab.fitAddon && tab.fitAddon.fit(), 50);
      });
    }
  }

  function closeTab(id) {
    const tab = tabs.get(id);
    if (!tab) return;
    if (tab.ws && tab.ws.readyState === WebSocket.OPEN) {
      tab.ws.close();
    }
    if (tab.usageTimer) window.clearInterval(tab.usageTimer);
    tab.term.dispose();
    tab.wrap.remove();
    tab.panel.remove();
    tabs.delete(id);
    const gi = gridPanelIds.indexOf(id);
    if (gi !== -1) gridPanelIds.splice(gi, 1);
    const remaining = [...tabs.keys()];
    if (remaining.length) activateTab(remaining[remaining.length - 1]);
  }

  /**
   * @param {string} agent
   * @param {number} port
   * @param {string} token
   * @param {{ sessionId?: string, injectSnippet?: boolean, reuse?: boolean, yolo?: boolean, profile?: string, host?: string, sessionType?: string, sshNode?: string, label?: string, onOpen?: function }} options
   */
  // Shared right-click context menu for all terminal panels
  let ctxMenu = null;
  function ensureContextMenu() {
    if (ctxMenu) return ctxMenu;
    ctxMenu = document.createElement("div");
    ctxMenu.id = "terminal-context-menu";
    Object.assign(ctxMenu.style, {
      position: "fixed",
      zIndex: "9999",
      background: "#2d2d2d",
      border: "1px solid #555",
      borderRadius: "4px",
      padding: "4px 0",
      boxShadow: "0 2px 8px rgba(0,0,0,0.5)",
      display: "none",
      minWidth: "120px",
      fontFamily: "system-ui, sans-serif",
      fontSize: "13px",
      color: "#ddd",
    });

    function makeItem(label, action) {
      const el = document.createElement("div");
      el.textContent = label;
      Object.assign(el.style, {
        padding: "6px 16px",
        cursor: "pointer",
        userSelect: "none",
      });
      el.addEventListener("mouseenter", () => el.style.background = "#444");
      el.addEventListener("mouseleave", () => el.style.background = "");
      el.addEventListener("mousedown", (e) => { e.preventDefault(); action(); hideContextMenu(); });
      return el;
    }

    ctxMenu._copyItem = makeItem("Copy", () => {
      const sel = getActiveSelection();
      if (sel) navigator.clipboard.writeText(sel).catch(() => {});
    });
    ctxMenu._pasteItem = makeItem("Paste", () => {
      navigator.clipboard.readText().then((text) => {
        if (text) sendToActiveTerminal(text);
      }).catch(() => {});
    });

    ctxMenu.appendChild(ctxMenu._copyItem);
    ctxMenu.appendChild(ctxMenu._pasteItem);
    document.body.appendChild(ctxMenu);

    document.addEventListener("mousedown", (e) => {
      if (!ctxMenu.contains(e.target)) hideContextMenu();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") hideContextMenu();
    });

    return ctxMenu;
  }

  function showContextMenu(x, y) {
    const menu = ensureContextMenu();
    const hasSel = Boolean(getActiveSelection());
    menu._copyItem.style.opacity = hasSel ? "1" : "0.4";
    menu._copyItem.style.pointerEvents = hasSel ? "" : "none";
    menu.style.display = "block";
    menu.style.left = x + "px";
    menu.style.top = y + "px";
    // Keep within viewport
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) menu.style.left = (x - rect.width) + "px";
    if (rect.bottom > window.innerHeight) menu.style.top = (y - rect.height) + "px";
  }

  function hideContextMenu() {
    if (ctxMenu) ctxMenu.style.display = "none";
  }

  function selectWordAtMouse(term, clientX, clientY) {
    if (!term.element) return;
    const rect = term.element.getBoundingClientRect();
    const cellW = rect.width / term.cols;
    const cellH = rect.height / term.rows;
    const col = Math.floor((clientX - rect.left) / cellW);
    const row = Math.floor((clientY - rect.top) / cellH);
    if (row < 0 || row >= term.rows || col < 0 || col >= term.cols) return;

    const bufRow = term.buffer.active.viewportY + row;
    const line = term.buffer.active.getLine(bufRow);
    if (!line) return;

    const text = line.translateToString(true);
    if (!text) return;

    const safeCol = Math.min(col, text.length - 1);
    if (safeCol < 0) return;

    // Only select if we landed on a non-space character
    if (!/\S/.test(text[safeCol])) return;

    let start = safeCol;
    while (start > 0 && /\S/.test(text[start - 1])) start--;
    let end = safeCol;
    while (end < text.length - 1 && /\S/.test(text[end + 1])) end++;

    term.select(start, bufRow, end - start + 1);
  }

  function openTerminal(agent, port, token, options) {
    options = options || {};
    const sessionId = options.sessionId || null;
    const sessionType = options.sessionType || (options.sshNode ? "ssh" : "agent");
    const sshNode = options.sshNode || null;
    const labelText = options.label || (sessionType === "ssh" ? `SSH ${sshNode}` : agent);
    const injectSnippet = Boolean(options.injectSnippet);
    const reuse = options.reuse === true;
    const yolo = Boolean(options.yolo);
    const profile = options.profile || null;
    const resumeSessionId = options.resumeSessionId || null;
    const host = options.host || "127.0.0.1";

    if (!global.Terminal || !global.FitAddon) {
      throw new Error("xterm.js not loaded");
    }
    const id = `t${++tabCounter}`;

    const wrap = document.createElement("div");
    wrap.className = "terminal-tab";
    wrap.setAttribute("role", "tab");
    if (sessionType === "agent" && global.AgentRelayColors) {
      global.AgentRelayColors.applyAgentColor(wrap, agent);
    }

    const label = document.createElement("button");
    label.type = "button";
    label.className = "terminal-tab-label";
    const swatch = document.createElement("span");
    swatch.className = "agent-swatch";
    label.appendChild(swatch);
    label.appendChild(document.createTextNode(labelText));
    label.title = `Show ${labelText}`;
    label.addEventListener("click", () => activateTab(id));

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "terminal-tab-close";
    closeBtn.setAttribute("aria-label", `Close ${labelText} tab`);
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
    const viewport = document.createElement("div");
    viewport.className = "terminal-viewport";
    const usageStrip = document.createElement("div");
    usageStrip.className = "terminal-usage";
    const usageText = document.createElement("span");
    usageText.className = "terminal-usage-text";
    usageText.textContent = sessionType === "agent" ? "Usage unavailable" : "SSH session";
    usageStrip.appendChild(usageText);
    const usageRefresh = document.createElement("button");
    usageRefresh.type = "button";
    usageRefresh.className = "terminal-usage-refresh";
    usageRefresh.textContent = "Refresh";
    usageRefresh.title = "Refresh Claude usage";
    usageRefresh.hidden = !(sessionType === "agent" && isClaudeAgent(agent));
    usageStrip.appendChild(usageRefresh);
    panel.appendChild(viewport);
    panel.appendChild(usageStrip);
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Consolas", "Courier New", monospace',
      theme: XTERM_THEME,
      allowTransparency: false,
    });
    const vtDecoder = new TextDecoder("utf-8", { fatal: false });
    const writeVt = (b64) => {
      if (!b64) return;
      term.write(vtDecoder.decode(b64ToBytes(b64)));
    };
    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(viewport);

    panel.addEventListener("mousedown", () => {
      if (currentLayout !== "1") activateTab(id);
    });

    viewport.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      if (!term.getSelection()) selectWordAtMouse(term, e.clientX, e.clientY);
      showContextMenu(e.clientX, e.clientY);
    });

    tabs.set(id, {
      wrap,
      panel,
      term,
      fitAddon,
      ws: null,
      agent,
      sessionType,
      sshNode,
      usageStrip,
      usageRefresh,
      usageTimer: null,
      host,
      port,
      token,
      sessionId: null,
    });
    tabsEl().appendChild(wrap);
    panelsEl().appendChild(panel);
    usageRefresh.addEventListener("click", () => requestUsageRefresh(tabs.get(id)));
    activateTab(id);
    fitAddon.fit();

    const ws = new WebSocket(wsUrl(host, port, token));
    tabs.get(id).ws = ws;

    ws.onopen = () => {
      const msg = sessionId
        ? { type: "open", session_id: sessionId }
        : sessionType === "ssh"
          ? {
              type: "open",
              session_id: null,
              session_type: "ssh",
              ssh_node: sshNode,
              cols: term.cols,
              rows: term.rows,
              reuse,
            }
        : {
            type: "open",
            session_id: null,
            session_type: "agent",
            agent,
            cols: term.cols,
            rows: term.rows,
            inject_snippet: injectSnippet,
            reuse,
            yolo,
            profile,
            resume_session_id: resumeSessionId,
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
          if (frame.scrollback) writeVt(frame.scrollback);
          fitAddon.fit();
          startUsagePolling(tab);
          if (typeof options.onOpen === "function") options.onOpen(frame);
          if (tab.sessionType === "agent") {
            const host = tab.host || "127.0.0.1";
            flushPendingForAgent(tab.agent, tab.port || port, tab.token || token);
          }
          break;
        case "data":
          if (frame.data) writeVt(frame.data);
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

  function startUsagePolling(tab) {
    if (!tab || tab.sessionType !== "agent" || !tab.sessionId || tab.usageTimer) return;
    const refresh = () => refreshUsage(tab);
    refresh();
    tab.usageTimer = window.setInterval(refresh, 5000);
  }

  function refreshUsage(tab) {
    if (!tab || !tab.sessionId || !tab.usageStrip) return;
    const path = `/api/terminal/sessions/${encodeURIComponent(tab.sessionId)}/usage`;
    fetch(httpUrl(tab.host || "127.0.0.1", tab.port, path, tab.token))
      .then((r) => r.ok ? r.json() : null)
      .then((usage) => {
        if (!usage) return;
        renderUsage(tab.usageStrip, usage);
      })
      .catch(() => {});
  }

  function requestUsageRefresh(tab) {
    if (!tab || tab.sessionType !== "agent" || !tab.sessionId || !isClaudeAgent(tab.agent)) return;
    setUsageText(tab.usageStrip, "Refreshing usage...");
    const path = `/api/terminal/sessions/${encodeURIComponent(tab.sessionId)}/usage/refresh`;
    fetch(httpUrl(tab.host || "127.0.0.1", tab.port, path, tab.token), { method: "POST" })
      .then((r) => {
        if (!r.ok) throw new Error("usage refresh failed");
        window.setTimeout(() => refreshUsage(tab), 800);
      })
      .catch(() => setUsageText(tab.usageStrip, "Usage refresh failed"));
  }

  function isClaudeAgent(agent) {
    return String(agent || "").toLowerCase().includes("claude");
  }

  function setUsageText(el, text) {
    const textEl = el && el.querySelector ? el.querySelector(".terminal-usage-text") : null;
    if (textEl) textEl.textContent = text;
    else if (el) el.textContent = text;
  }

  function formatTokens(value, approx) {
    if (value === null || value === undefined) return null;
    if (value >= 1_000_000) return `${approx ? "~" : ""}${(value / 1_000_000).toFixed(1)}m`;
    if (value >= 1_000) return `${approx ? "~" : ""}${Math.round(value / 1_000)}k`;
    return `${approx ? "~" : ""}${value}`;
  }

  function formatEta(seconds) {
    if (seconds === null || seconds === undefined) return null;
    const minutes = Math.max(1, Math.round(seconds / 60));
    return `~${minutes} min`;
  }

  function renderUsage(el, usage) {
    if (usage.summary) {
      setUsageText(el, usage.summary);
      el.classList.remove("warn");
      return;
    }
    if (usage.source === "none" || usage.used === null || usage.used === undefined) {
      setUsageText(el, "Usage unavailable");
      el.classList.remove("warn");
      return;
    }
    const parts = [`Used ${formatTokens(usage.used)}`];
    const left = formatTokens(usage.remaining, true);
    const eta = formatEta(usage.eta_seconds);
    if (left) parts.push(`Left ${left}`);
    if (eta) parts.push(eta);
    if (usage.tokens_per_minute) parts.push(`${Math.round(usage.tokens_per_minute)}/min`);
    setUsageText(el, parts.join(" | "));
    const low = (
      usage.remaining !== null
      && usage.remaining !== undefined
      && usage.limit
      && usage.remaining / usage.limit < 0.1
    );
    el.classList.toggle("warn", Boolean(low));
  }

  function openSshTerminal(nodeName, port, token, options) {
    options = options || {};
    if (!nodeName) return null;
    return openTerminal(`ssh:${nodeName}`, port, token, {
      ...options,
      sessionType: "ssh",
      sshNode: nodeName,
      label: options.label || `SSH ${nodeName}`,
      injectSnippet: false,
      yolo: false,
      profile: null,
    });
  }

  function isFocusedPanel(tab) {
    return tab.panel.classList.contains("active") || tab.panel.classList.contains("grid-focused");
  }

  function getActiveSelection() {
    let selection = "";
    tabs.forEach((tab) => {
      if (isFocusedPanel(tab)) selection = tab.term.getSelection();
    });
    return selection;
  }

  function clearActiveTerminal() {
    tabs.forEach((tab) => {
      if (isFocusedPanel(tab)) tab.term.clear();
    });
  }

  function sendToActiveTerminal(text) {
    let sent = false;
    tabs.forEach((tab) => {
      if (isFocusedPanel(tab)) sent = sendInput(tab, text) || sent;
    });
    return sent;
  }

  // Wire layout buttons
  document.querySelectorAll(".terminal-layout-btn").forEach(btn => {
    btn.addEventListener("click", () => setLayout(btn.dataset.layout));
  });

  global.AgentRelayTerminals = {
    openTerminal,
    openSshTerminal,
    closeTab,
    deliverToAgent,
    getActiveSelection,
    clearActiveTerminal,
    sendToActiveTerminal,
    setLayout,
  };
})(window);
