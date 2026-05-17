/**
 * Embedded xterm.js panes — connects to AgentRelay /terminal WebSocket.
 * Token is passed as a query parameter (browser WebSocket cannot set headers).
 */
(function (global) {
  const tabsEl = () => document.getElementById("terminal-tabs");
  const panelsEl = () => document.getElementById("terminal-panels");
  const _D = "di" + "v";

  let tabCounter = 0;
  const tabs = new Map();
  /** @type {Map<string, string>} mountKey → tab id */
  const embeddedByMount = new Map();
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
  /** @type {number} percent for first pane / first column / first row */
  const splitRatios = { "2h": 50, "2v": 50, "4-col": 50, "4-rowA": 50, "4-rowB": 50 };
  let splitRoot = null;
  let panelsResizeObserver = null;

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

  function isMainTerminalTab(tab) {
    return tab && !tab.embedded;
  }

  function shellEl() {
    return document.querySelector("#view-terminals .terminal-shell");
  }

  function maxSplitSlots() {
    return currentLayout === "4" ? 4 : 2;
  }

  function mainTabIds() {
    return [...tabs.keys()].filter((k) => isMainTerminalTab(tabs.get(k)));
  }

  function seedGridPanelIds() {
    const max = maxSplitSlots();
    gridPanelIds.length = 0;
    mainTabIds().slice(-max).forEach((id) => gridPanelIds.push(id));
  }

  function fitAllVisiblePanes() {
    tabs.forEach((tab) => {
      if (!isMainTerminalTab(tab)) return;
      const show = currentLayout === "1"
        ? tab.panel.classList.contains("active")
        : tab.panel.classList.contains("grid-visible");
      if (show && tab.fitAddon) tab.fitAddon.fit();
    });
  }

  function ensurePanelsResizeObserver() {
    const panels = panelsEl();
    if (!panels || panelsResizeObserver) return;
    panelsResizeObserver = new ResizeObserver(() => fitAllVisiblePanes());
    panelsResizeObserver.observe(panels);
  }

  function showTabsBtn() {
    return document.getElementById("btn-terminal-show-tabs");
  }

  function updateSplitShellClass() {
    const shell = shellEl();
    if (shell) shell.classList.toggle("terminal-shell--split", currentLayout !== "1");
    const tabsBtn = showTabsBtn();
    if (tabsBtn) tabsBtn.hidden = currentLayout === "1";
  }

  function swapSplitSlots(fromSlot, toSlot) {
    if (fromSlot === toSlot) return;
    const max = maxSplitSlots();
    while (gridPanelIds.length < max) gridPanelIds.push(null);
    const tmp = gridPanelIds[fromSlot];
    gridPanelIds[fromSlot] = gridPanelIds[toSlot];
    gridPanelIds[toSlot] = tmp;
  }

  function bindPaneReorder(handle, paneEl) {
    handle.addEventListener("dragstart", (e) => {
      const slot = parseInt(paneEl.dataset.slot, 10);
      e.dataTransfer.setData("application/x-agentrelay-slot", String(slot));
      e.dataTransfer.effectAllowed = "move";
      paneEl.classList.add("terminal-split-pane--dragging");
    });
    handle.addEventListener("dragend", () => {
      paneEl.classList.remove("terminal-split-pane--dragging");
      splitRoot?.querySelectorAll(".terminal-split-pane").forEach((p) => {
        p.classList.remove("terminal-split-pane--drop-target");
      });
    });
    paneEl.addEventListener("dragover", (e) => {
      if (!e.dataTransfer.types.includes("application/x-agentrelay-slot")) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      paneEl.classList.add("terminal-split-pane--drop-target");
    });
    paneEl.addEventListener("dragleave", (e) => {
      if (!paneEl.contains(e.relatedTarget)) {
        paneEl.classList.remove("terminal-split-pane--drop-target");
      }
    });
    paneEl.addEventListener("drop", (e) => {
      e.preventDefault();
      paneEl.classList.remove("terminal-split-pane--drop-target");
      const from = parseInt(e.dataTransfer.getData("application/x-agentrelay-slot"), 10);
      const to = parseInt(paneEl.dataset.slot, 10);
      if (Number.isNaN(from) || Number.isNaN(to) || from === to) return;
      swapSplitSlots(from, to);
      const focusId = gridPanelIds[to] || gridPanelIds[from];
      syncSplitSlots(focusId);
    });
  }

  function teardownSplitLayout() {
    const panels = panelsEl();
    if (!panels) return;
    tabs.forEach((tab) => {
      if (!isMainTerminalTab(tab)) return;
      tab.panel.classList.remove("grid-visible", "grid-focused", "terminal-panel--split");
      panels.appendChild(tab.panel);
    });
    if (splitRoot) splitRoot.remove();
    splitRoot = null;
  }

  function applyFlexRatio(paneA, paneB, percent) {
    const p = Math.min(80, Math.max(20, percent));
    paneA.style.flex = `0 0 ${p}%`;
    paneB.style.flex = "1 1 0";
  }

  function bindSplitterDrag(splitter, paneA, paneB, ratioKey, axis) {
    splitter.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const parent = splitter.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      const size = axis === "x" ? rect.width : rect.height;
      const origin = axis === "x" ? rect.left : rect.top;

      function onMove(ev) {
        const pos = axis === "x" ? ev.clientX : ev.clientY;
        const pct = ((pos - origin) / size) * 100;
        splitRatios[ratioKey] = pct;
        applyFlexRatio(paneA, paneB, pct);
        fitAllVisiblePanes();
      }

      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }

      document.body.style.cursor = axis === "x" ? "col-resize" : "row-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  function createSplitter(orientation, ratioKey, paneA, paneB) {
    const el = document.createElement(_D);
    el.className = `terminal-splitter terminal-splitter-${orientation}`;
    el.setAttribute("role", "separator");
    el.title = "Drag to resize";
    bindSplitterDrag(el, paneA, paneB, ratioKey, orientation === "v" ? "x" : "y");
    return el;
  }

  function createSplitPane(slotIndex) {
    const pane = document.createElement(_D);
    pane.className = "terminal-split-pane";
    pane.dataset.slot = String(slotIndex);
    const chrome = document.createElement(_D);
    chrome.className = "terminal-pane-chrome";
    const dragHandle = document.createElement("span");
    dragHandle.className = "terminal-pane-drag";
    dragHandle.draggable = true;
    dragHandle.setAttribute("aria-label", "Drag to reorder pane");
    dragHandle.title = "Drag to reorder";
    dragHandle.textContent = "⋮⋮";
    const title = document.createElement("span");
    title.className = "terminal-pane-title";
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "terminal-pane-close";
    closeBtn.setAttribute("aria-label", "Close terminal");
    closeBtn.title = "Close";
    closeBtn.innerHTML = "&times;";
    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = gridPanelIds[slotIndex];
      if (tabId) closeTab(tabId);
    });
    chrome.appendChild(dragHandle);
    chrome.appendChild(title);
    chrome.appendChild(closeBtn);
    const body = document.createElement(_D);
    body.className = "terminal-split-pane-body";
    pane.appendChild(chrome);
    pane.appendChild(body);
    pane._titleEl = title;
    pane._bodyEl = body;
    bindPaneReorder(dragHandle, pane);
    chrome.addEventListener("mousedown", (e) => {
      if (e.target.closest(".terminal-pane-close, .terminal-pane-drag")) return;
      const tabId = gridPanelIds[slotIndex];
      if (tabId) activateTab(tabId);
    });
    return pane;
  }

  function buildSplitLayout(layout) {
    const panels = panelsEl();
    if (!panels) return;
    teardownSplitLayout();
    splitRoot = document.createElement(_D);
    splitRoot.className = "terminal-split-root";

    if (layout === "2h") {
      splitRoot.classList.add("terminal-split-h");
      const pane0 = createSplitPane(0);
      const pane1 = createSplitPane(1);
      const splitter = createSplitter("v", "2h", pane0, pane1);
      splitRoot.appendChild(pane0);
      splitRoot.appendChild(splitter);
      splitRoot.appendChild(pane1);
      applyFlexRatio(pane0, pane1, splitRatios["2h"]);
    } else if (layout === "2v") {
      splitRoot.classList.add("terminal-split-v");
      const pane0 = createSplitPane(0);
      const pane1 = createSplitPane(1);
      const splitter = createSplitter("h", "2v", pane0, pane1);
      splitRoot.appendChild(pane0);
      splitRoot.appendChild(splitter);
      splitRoot.appendChild(pane1);
      applyFlexRatio(pane0, pane1, splitRatios["2v"]);
    } else if (layout === "4") {
      splitRoot.classList.add("terminal-split-4");
      const colA = document.createElement(_D);
      colA.className = "terminal-split-col";
      const colB = document.createElement(_D);
      colB.className = "terminal-split-col";
      const rowA = document.createElement(_D);
      rowA.className = "terminal-split-v";
      const rowB = document.createElement(_D);
      rowB.className = "terminal-split-v";
      const p0 = createSplitPane(0);
      const p1 = createSplitPane(1);
      const p2 = createSplitPane(2);
      const p3 = createSplitPane(3);
      const splitA = createSplitter("h", "4-rowA", p0, p1);
      const splitB = createSplitter("h", "4-rowB", p2, p3);
      const splitCol = createSplitter("v", "4-col", colA, colB);
      rowA.appendChild(p0);
      rowA.appendChild(splitA);
      rowA.appendChild(p1);
      rowB.appendChild(p2);
      rowB.appendChild(splitB);
      rowB.appendChild(p3);
      colA.appendChild(rowA);
      colB.appendChild(rowB);
      splitRoot.appendChild(colA);
      splitRoot.appendChild(splitCol);
      splitRoot.appendChild(colB);
      applyFlexRatio(colA, colB, splitRatios["4-col"]);
      applyFlexRatio(p0, p1, splitRatios["4-rowA"]);
      applyFlexRatio(p2, p3, splitRatios["4-rowB"]);
    }

    panels.appendChild(splitRoot);
  }

  function assignTabToSplit(id, focusId) {
    const max = maxSplitSlots();
    if (!gridPanelIds.includes(id)) {
      const empty = gridPanelIds.indexOf(null);
      if (empty !== -1) gridPanelIds[empty] = id;
      else if (gridPanelIds.length < max) gridPanelIds.push(id);
      else gridPanelIds[max - 1] = id;
    }
    syncSplitSlots(focusId || id);
  }

  function syncSplitSlots(focusId) {
    if (!splitRoot || currentLayout === "1") return;
    const slots = splitRoot.querySelectorAll(".terminal-split-pane");
    const max = maxSplitSlots();
    while (gridPanelIds.length < max) gridPanelIds.push(null);

    tabs.forEach((tab) => {
      if (!isMainTerminalTab(tab)) return;
      tab.panel.classList.remove("active", "grid-visible", "grid-focused");
    });

    slots.forEach((slot, i) => {
      const body = slot._bodyEl || slot.querySelector(".terminal-split-pane-body");
      const titleEl = slot._titleEl || slot.querySelector(".terminal-pane-title");
      if (!body) return;
      body.innerHTML = "";
      const tabId = gridPanelIds[i];
      if (tabId && tabs.has(tabId)) {
        const tab = tabs.get(tabId);
        tab.panel.classList.add("grid-visible", "terminal-panel--split");
        body.appendChild(tab.panel);
        if (titleEl) titleEl.textContent = tab.agent || "Terminal";
        if (tab.wrap) tab.wrap.classList.toggle("active", tabId === focusId);
      } else if (titleEl) {
        titleEl.textContent = "Empty";
        body.innerHTML = '<p class="terminal-split-empty hint">Open another tab to fill this pane</p>';
      }
    });

    const focus = focusId || gridPanelIds[0];
    if (focus) {
      tabs.forEach((tab, key) => {
        if (!isMainTerminalTab(tab)) return;
        tab.panel.classList.toggle("grid-focused", key === focus);
        if (tab.wrap) tab.wrap.classList.toggle("active", key === focus);
      });
    }
    window.setTimeout(fitAllVisiblePanes, 30);
  }

  function activateTab(id) {
    const target = tabs.get(id);
    if (!target || !isMainTerminalTab(target)) return;

    if (currentLayout !== "1") {
      tabs.forEach((tab, key) => {
        if (!isMainTerminalTab(tab)) return;
        tab.panel.classList.toggle("grid-focused", key === id);
        if (tab.wrap) tab.wrap.classList.toggle("active", key === id);
      });
      const tab = tabs.get(id);
      if (tab?.fitAddon) setTimeout(() => tab.fitAddon.fit(), 30);
      return;
    }
    tabs.forEach((tab, key) => {
      if (!isMainTerminalTab(tab)) return;
      if (tab.wrap) tab.wrap.classList.toggle("active", key === id);
      tab.panel.classList.toggle("active", key === id);
      if (key === id && tab.fitAddon) setTimeout(() => tab.fitAddon.fit(), 50);
    });
  }

  function setLayout(layout) {
    currentLayout = layout;
    const panels = panelsEl();
    if (!panels) return;
    panels.className = "terminal-panels";
    document.querySelectorAll(".terminal-layout-btn").forEach((b) =>
      b.classList.toggle("active", b.dataset.layout === layout));
    updateSplitShellClass();
    ensurePanelsResizeObserver();

    if (layout === "1") {
      gridPanelIds.length = 0;
      teardownSplitLayout();
      const ids = mainTabIds();
      if (ids.length) activateTab(ids[ids.length - 1]);
    } else {
      if (!gridPanelIds.length) seedGridPanelIds();
      buildSplitLayout(layout);
      syncSplitSlots(gridPanelIds[0] || mainTabIds().slice(-1)[0]);
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
    if (tab.wrap) tab.wrap.remove();
    tab.panel.remove();
    if (tab.embeddedMountKey) embeddedByMount.delete(tab.embeddedMountKey);
    tabs.delete(id);
    const gi = gridPanelIds.indexOf(id);
    if (gi !== -1) gridPanelIds[gi] = null;
    const remaining = mainTabIds();
    if (currentLayout !== "1") {
      syncSplitSlots(remaining[remaining.length - 1]);
    } else if (remaining.length) {
      activateTab(remaining[remaining.length - 1]);
    }
  }

  function fitEmbeddedTab(id) {
    const tab = tabs.get(id);
    if (tab?.fitAddon) {
      setTimeout(() => tab.fitAddon.fit(), 50);
    }
  }

  function embeddedTabLive(id) {
    const tab = tabs.get(id);
    return Boolean(
      tab
      && tab.ws
      && tab.ws.readyState === WebSocket.OPEN
      && tab.connected
    );
  }

  function openEmbeddedTerminal(mountKey, container, agent, port, token, options) {
    options = options || {};
    if (!container) throw new Error("container required");
    if (!token) throw new Error("Missing auth token");
    const existingId = embeddedByMount.get(mountKey);
    if (existingId && tabs.has(existingId)) {
      const existing = tabs.get(existingId);
      if (existing.agent === agent && embeddedTabLive(existingId)) {
        fitEmbeddedTab(existingId);
        return existingId;
      }
      closeTab(existingId);
    }
    container.innerHTML = "";
    const shell = document.createElement("di" + "v");
    shell.className = "ideas-terminal-shell terminal-shell";
    const panels = document.createElement("di" + "v");
    panels.className = "terminal-panels ideas-terminal-panels";
    shell.appendChild(panels);
    container.appendChild(shell);
    const id = openTerminal(agent, port, token, {
      ...options,
      embedded: true,
      mountKey,
      panelsParent: panels,
      skipTabBar: true,
    });
    embeddedByMount.set(mountKey, id);
    fitEmbeddedTab(id);
    return id;
  }

  function closeEmbeddedForMount(mountKey) {
    const id = embeddedByMount.get(mountKey);
    if (id) closeTab(id);
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
    const embedded = Boolean(options.embedded);
    const skipTabBar = Boolean(options.skipTabBar);
    const panelsParent = options.panelsParent || panelsEl();
    const mountKey = options.mountKey || null;

    if (!global.Terminal || !global.FitAddon) {
      throw new Error("xterm.js not loaded");
    }
    const id = `t${++tabCounter}`;

    let wrap = null;
    if (!skipTabBar) {
    wrap = document.createElement("div");
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
    tabsEl().appendChild(wrap);
    }

    const panel = document.createElement("di" + "v");
    panel.className = "terminal-panel" + (embedded ? " active embedded-panel" : "");
    panel.id = `panel-${id}`;
    if (embedded) {
      panel.style.position = "relative";
      panel.style.inset = "auto";
      panel.style.display = "flex";
    }
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
      embedded,
      embeddedMountKey: mountKey,
    });
    panelsParent.appendChild(panel);
    usageRefresh.addEventListener("click", () => requestUsageRefresh(tabs.get(id)));
    if (skipTabBar) {
      fitAddon.fit();
    } else if (currentLayout !== "1") {
      assignTabToSplit(id, id);
    } else {
      activateTab(id);
      fitAddon.fit();
    }

    const tabState = tabs.get(id);
    const connectWs = () => {
      if (tabState.ws) {
        try { tabState.ws.close(); } catch (_) { /* ignore */ }
      }
      const ws = new WebSocket(wsUrl(host, port, token));
      tabState.ws = ws;
      tabState.connected = false;

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
            tab.connected = true;
            tab.sessionId = frame.session_id;
            tab.writeToken = frame.write_token;
            term.clear();
            if (frame.scrollback) writeVt(frame.scrollback);
            fitAddon.fit();
            startUsagePolling(tab);
            if (typeof options.onOpen === "function") options.onOpen(frame);
            if (tab.sessionType === "agent") {
              const tabHost = tab.host || "127.0.0.1";
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

      ws.onerror = () => {
        if (!tabState.connected) {
          term.writeln("\r\n\x1b[31m[connection failed — check relay is running and reopen from AgentRelay app]\x1b[0m");
        }
      };

      ws.onclose = (ev) => {
        if (!tabState.connected) {
          const hint = ev.code === 1006 || ev.code === 1002
            ? "connection refused or auth failed"
            : `closed (${ev.code})`;
          term.writeln(`\r\n\x1b[31m[${hint} — reopen UI from AgentRelay desktop app]\x1b[0m`);
          return;
        }
        term.writeln("\r\n\x1b[90m[disconnected]\x1b[0m");
      };
    };

    term.onData((data) => {
      const tab = tabs.get(id);
      const ws = tab?.ws;
      if (!tab || !tab.writeToken || !ws || ws.readyState !== WebSocket.OPEN) return;
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
      const ws = tab?.ws;
      if (!tab || !tab.writeToken || !ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({
        type: "resize",
        session_id: tab.sessionId,
        write_token: tab.writeToken,
        cols,
        rows,
      }));
    });

    if (embedded) {
      requestAnimationFrame(() => {
        fitAddon.fit();
        connectWs();
      });
    } else {
      connectWs();
    }

    window.addEventListener("resize", () => {
      const tab = tabs.get(id);
      if (!tab) return;
      const visible = tab.embedded
        ? tab.panel.classList.contains("embedded-panel")
        : tab.panel.classList.contains("active") || tab.panel.classList.contains("grid-visible");
      if (visible) fitAddon.fit();
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
    if (tab.embedded) return true;
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
  const tabsModeBtn = showTabsBtn();
  if (tabsModeBtn) {
    tabsModeBtn.addEventListener("click", () => setLayout("1"));
  }

  global.AgentRelayTerminals = {
    openTerminal,
    openEmbeddedTerminal,
    openSshTerminal,
    closeTab,
    closeEmbeddedForMount,
    deliverToAgent,
    getActiveSelection,
    clearActiveTerminal,
    sendToActiveTerminal,
    setLayout,
    fitEmbeddedTab,
  };
})(window);
