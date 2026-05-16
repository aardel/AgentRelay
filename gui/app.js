/** AgentRelay local web UI — talks to the embedded daemon on localhost. */

const params = new URLSearchParams(window.location.search);
const AUTH_TOKEN = params.get("token") || sessionStorage.getItem("agentrelay_token") || "";
const API_PORT = parseInt(params.get("port") || "9876", 10);

if (AUTH_TOKEN) {
  sessionStorage.setItem("agentrelay_token", AUTH_TOKEN);
}

const el = (id) => document.getElementById(id);
let sendTargets = [];
let lastInboxTs = 0;

const YOLO_STORAGE_KEY = "agentrelay_yolo_mode";

function isYoloEnabled() {
  return sessionStorage.getItem(YOLO_STORAGE_KEY) === "1";
}

function setYoloEnabled(on) {
  sessionStorage.setItem(YOLO_STORAGE_KEY, on ? "1" : "0");
  const hint = el("yolo-hint");
  if (hint) hint.hidden = !on;
  for (const id of ["yolo-mode", "yolo-mode-terminals"]) {
    const box = el(id);
    if (box) box.checked = on;
  }
}

function syncYoloCheckboxes() {
  const on = isYoloEnabled();
  for (const id of ["yolo-mode", "yolo-mode-terminals"]) {
    const box = el(id);
    if (box) box.checked = on;
  }
  const hint = el("yolo-hint");
  if (hint) hint.hidden = !on;
}

function setFooter(msg) {
  el("footer").textContent = msg || "";
}

async function api(path, opts = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Agent-Token": AUTH_TOKEN,
    ...(opts.headers || {}),
  };
  const r = await fetch(`http://127.0.0.1:${API_PORT}${path}`, { ...opts, headers });
  let data = {};
  try {
    data = await r.json();
  } catch {
    data = {};
  }
  return { ok: r.ok, status: r.status, data };
}

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
  const view = el(`view-${name}`);
  const nav = document.querySelector(`.nav-item[data-view="${name}"]`);
  if (view) view.classList.add("active");
  if (nav) nav.classList.add("active");
}

function setRelay(on) {
  el("status-badge").textContent = on ? "Running" : "Stopped";
  el("status-badge").className = on ? "badge on" : "badge off";
}

function renderAgents(agents) {
  const ul = el("local-agents");
  const launch = el("launch-agent");
  const termAgent = el("terminal-agent");
  ul.innerHTML = "";
  launch.innerHTML = "";
  termAgent.innerHTML = "";
  if (!agents.length) {
    ul.innerHTML = "<li>No agents configured</li>";
    return;
  }
  for (const a of agents) {
    const li = document.createElement("li");
    const kind = a.mode === "visible" ? "Interactive" : "Background";
    const extra = a.role ? ` · ${a.role}` : "";
    li.innerHTML = `<strong>${a.label || a.id}</strong><br><span class="hint">${kind}${extra}</span>`;
    ul.appendChild(li);

    for (const select of [launch, termAgent]) {
      const opt = document.createElement("option");
      opt.value = a.id;
      opt.textContent = a.label || a.id;
      select.appendChild(opt);
    }
  }
}

function renderNearby(list) {
  const ul = el("nearby-list");
  ul.innerHTML = "";
  if (!list.length) {
    ul.innerHTML = '<li class="empty">No other computers found. Start AgentRelay on them too.</li>';
    return;
  }
  for (const p of list) {
    const li = document.createElement("li");
    const agents = Array.isArray(p.agents)
      ? p.agents.join(", ")
      : String(p.agents || "").replace(/,/g, ", ");
    li.innerHTML = `
      <div class="peer-row">
        <div>
          <div class="peer-name">${p.name}</div>
          <div class="peer-meta">${agents || "Agent relay"}</div>
        </div>
        <div>
          ${p.connected
      ? '<span class="connected">Connected</span>'
      : `<button type="button" class="btn primary btn-connect" data-peer="${p.name}">Connect</button>`}
        </div>
      </div>`;
    ul.appendChild(li);
  }
  ul.querySelectorAll(".btn-connect").forEach((btn) => {
    btn.addEventListener("click", () => connect(btn.dataset.peer, btn));
  });
}

function agentListFromPeer(peer) {
  if (Array.isArray(peer.agents)) return peer.agents;
  return String(peer.agents || "").split(",").map((a) => a.trim()).filter(Boolean);
}

function renderSendTargets(data) {
  const targetSelect = el("send-target");
  const localAgents = (data.agents || []).map((a) => a.id).filter(Boolean);
  sendTargets = [{
    name: `This computer (${data.node || "local"})`,
    address: "127.0.0.1",
    port: data.port || API_PORT,
    agents: localAgents,
    local: true,
  }];
  for (const peer of data.nearby || []) {
    if (!peer.connected) continue;
    sendTargets.push({
      name: peer.name,
      address: peer.address,
      port: peer.port,
      agents: agentListFromPeer(peer),
      local: false,
    });
  }

  const previous = targetSelect.value;
  targetSelect.innerHTML = "";
  for (const target of sendTargets) {
    const option = document.createElement("option");
    option.value = target.name;
    option.textContent = target.name;
    targetSelect.appendChild(option);
  }
  if (sendTargets.some((t) => t.name === previous)) {
    targetSelect.value = previous;
  }
  renderSendAgents();
}

function renderSendAgents() {
  const selected = sendTargets.find((t) => t.name === el("send-target").value);
  const agents = selected ? selected.agents : [];
  const agentSelect = el("send-agent");
  agentSelect.innerHTML = "";
  for (const agent of agents) {
    const option = document.createElement("option");
    option.value = agent;
    option.textContent = agent;
    agentSelect.appendChild(option);
  }
}

function renderPending(list) {
  const card = el("pending-card");
  const ul = el("pending-list");
  if (!list.length) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  ul.innerHTML = "";
  for (const p of list) {
    const li = document.createElement("li");
    li.className = "peer-row";
    li.innerHTML = `
      <span><strong>${p.from_node}</strong> wants to connect</span>
      <button type="button" class="btn primary" data-id="${p.id}" data-peer="${p.from_node}">Allow</button>`;
    li.querySelector("button").addEventListener("click", async (e) => {
      const b = e.target;
      b.disabled = true;
      await api("/api/approve", {
        method: "POST",
        body: JSON.stringify({ request_id: p.id, peer_name: p.from_node }),
      });
      refresh();
    });
    ul.appendChild(li);
  }
}

function renderInbox(messages) {
  const log = el("inbox-log");
  if (!messages.length) {
    log.textContent = "(no messages yet)";
    return;
  }
  log.textContent = messages
    .map((m) => `[${new Date(m.ts * 1000).toLocaleTimeString()}] ${m.from} → ${m.agent || "?"}\n${m.command}`)
    .join("\n\n---\n\n");
  log.scrollTop = log.scrollHeight;
}

async function refresh() {
  if (!AUTH_TOKEN) {
    setRelay(false);
    setFooter("Missing token — restart the app from agentrelay-gui");
    return;
  }
  const { ok, data } = await api("/api/status");
  if (!ok) {
    setRelay(false);
    setFooter("Cannot reach relay — is the daemon running?");
    return;
  }
  setRelay(data.relay_running !== false);
  el("node-name").value = data.node || "";
  el("this-address").textContent = data.address
    ? `On your network at ${data.address}:${data.port || API_PORT}`
    : "";
  el("wait-seconds").value = data.wait_before_send_seconds || 5;
  renderAgents(data.agents || []);
  renderNearby(data.nearby || []);
  renderSendTargets(data);

  const pending = await api("/api/pending");
  renderPending(pending.data.pending || []);

  const snip = await api("/api/agent-snippet");
  el("agent-snippet").textContent = snip.data.snippet || "";

  const inbox = await api(`/api/inbox?since=${lastInboxTs}`);
  const messages = inbox.data.messages || [];
  if (messages.length) {
    lastInboxTs = Math.max(...messages.map((m) => m.ts));
    renderInbox(messages);
  }
}

async function connect(peer, btn) {
  btn.disabled = true;
  btn.textContent = "Connecting…";
  const { ok, data } = await api("/api/connect", {
    method: "POST",
    body: JSON.stringify({ peer }),
  });
  if (!ok) {
    setFooter(data.error || "Could not connect — approve on the other computer.");
    btn.disabled = false;
    btn.textContent = "Connect";
    return;
  }
  setFooter(`Connected to ${peer}`);
  refresh();
}

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

el("btn-refresh").addEventListener("click", refresh);

el("btn-save").addEventListener("click", async () => {
  await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      node_name: el("node-name").value.trim(),
      wait_before_send_seconds: parseInt(el("wait-seconds").value, 10) || 5,
    }),
  });
  setFooter("Settings saved");
  refresh();
});

el("btn-copy").addEventListener("click", () => {
  navigator.clipboard.writeText(el("agent-snippet").textContent);
  el("btn-copy").textContent = "Copied!";
  setTimeout(() => { el("btn-copy").textContent = "Copy"; }, 2000);
});

el("send-target").addEventListener("change", renderSendAgents);

el("btn-broadcast").addEventListener("click", async () => {
  const message = el("broadcast-message").value.trim();
  if (!message) {
    el("broadcast-status").textContent = "Enter a message to broadcast.";
    return;
  }
  const scope = el("broadcast-include-peers").checked ? "all" : "local";
  el("btn-broadcast").disabled = true;
  el("broadcast-status").textContent = "Broadcasting…";
  const { ok, data } = await api("/api/broadcast", {
    method: "POST",
    body: JSON.stringify({ message, scope }),
  });
  el("btn-broadcast").disabled = false;
  if (!ok) {
    el("broadcast-status").textContent = data.error || "Broadcast failed.";
    return;
  }
  const scopeLabel = scope === "all"
    ? "all local and connected agents"
    : "all local agents";
  el("broadcast-status").textContent =
    `Global broadcast sent to ${data.succeeded}/${data.sent_to} agents (${scopeLabel}).`;
  setFooter(`Global broadcast: ${data.succeeded}/${data.sent_to} delivered`);
  if (data.failed > 0 && data.results) {
    const failed = data.results
      .filter((r) => !r.ok)
      .map((r) => `${r.agent}@${r.node}`)
      .join(", ");
    el("broadcast-status").textContent += ` Failed: ${failed}`;
  }
  el("broadcast-message").value = "";
});

el("btn-send").addEventListener("click", async () => {
  const target = sendTargets.find((t) => t.name === el("send-target").value);
  const agent = el("send-agent").value;
  const message = el("send-message").value.trim();
  if (!target || !agent || !message) {
    el("send-status").textContent = "Choose a target, agent, and message.";
    return;
  }
  const { ok, data } = await api("/api/send", {
    method: "POST",
    body: JSON.stringify({
      agent,
      message,
      local: target.local,
      address: target.address,
      port: target.port,
    }),
  });
  el("send-status").textContent = ok
    ? (data.stdout || data.message || "Sent.")
    : (data.error || data.stderr || "Send failed.");
  if (ok) el("send-message").value = "";
});

function openAgentTerminal(agent, { injectSnippet = false, reuse = false } = {}) {
  if (!agent) return;
  showView("terminals");
  window.AgentRelayTerminals.openTerminal(agent, API_PORT, AUTH_TOKEN, {
    injectSnippet,
    reuse,
    yolo: isYoloEnabled(),
  });
}

el("btn-new-terminal").addEventListener("click", () => {
  const agent = el("terminal-agent").value;
  if (!agent) return;
  try {
    openAgentTerminal(agent, { injectSnippet: false, reuse: false });
    setFooter(`New terminal for ${agent}`);
  } catch (e) {
    setFooter(`Terminal error: ${e.message}`);
  }
});

el("btn-launch-agent").addEventListener("click", async () => {
  const agent = el("launch-agent").value;
  if (!agent) return;
  try {
    openAgentTerminal(agent, { injectSnippet: true, reuse: true });
    const snip = el("agent-snippet").textContent;
    if (snip) {
      try {
        await navigator.clipboard.writeText(snip);
      } catch {
        /* clipboard optional */
      }
    }
    setFooter(`Launched ${agent} — AgentRelay instructions pasted into terminal`);
  } catch (e) {
    setFooter(`Launch error: ${e.message}`);
  }
});

el("btn-open-terminal").addEventListener("click", () => {
  const agent = el("launch-agent").value;
  if (!agent) return;
  try {
    openAgentTerminal(agent, { injectSnippet: false, reuse: false });
    setFooter(`Opened fresh terminal for ${agent}`);
  } catch (e) {
    setFooter(`Terminal error: ${e.message}`);
  }
});

// ── Skills ───────────────────────────────────────────────────────────────────

let skillTarget = "Claude Code";

async function refreshSkills() {
  const { ok, data } = await api(`/api/skills?target=${encodeURIComponent(skillTarget)}`);
  if (!ok) return;

  const targetSelect = el("skill-target");
  if (data.targets && !targetSelect.options.length) {
    targetSelect.innerHTML = "";
    for (const t of data.targets) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      targetSelect.appendChild(opt);
    }
  }
  targetSelect.value = data.target || skillTarget;
  skillTarget = targetSelect.value;

  const ul = el("skills-list");
  ul.innerHTML = "";
  for (const skill of data.skills || []) {
    const li = document.createElement("li");
    li.className = "skill-row";
    const status = skill.installed ? "installed" : "";
    li.innerHTML = `
      <div>
        <strong>/${skill.name}</strong>
        <span class="hint">${skill.label}</span>
      </div>
      <div class="skill-actions">
        <span class="skill-status ${status}">${skill.installed ? "Installed" : ""}</span>
        <button type="button" class="btn ghost small" data-action="remove" data-name="${skill.name}">Remove</button>
        <button type="button" class="btn primary small" data-action="install" data-name="${skill.name}">Install</button>
      </div>`;
    ul.appendChild(li);
  }

  ul.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.name;
      const path = btn.dataset.action === "install"
        ? "/api/skills/install"
        : "/api/skills/remove";
      const { data: res } = await api(path, {
        method: "POST",
        body: JSON.stringify({ name, target: skillTarget }),
      });
      setFooter(res.message || "Done");
      refreshSkills();
    });
  });
}

el("skill-target").addEventListener("change", () => {
  skillTarget = el("skill-target").value;
  refreshSkills();
});

el("btn-skills-install-all").addEventListener("click", async () => {
  const { data } = await api("/api/skills/install-all", {
    method: "POST",
    body: JSON.stringify({ target: skillTarget }),
  });
  setFooter(`Installed ${(data.messages || []).length} skills for ${skillTarget}`);
  refreshSkills();
});

el("btn-skills-remove-all").addEventListener("click", async () => {
  const { data } = await api("/api/skills/remove-all", {
    method: "POST",
    body: JSON.stringify({ target: skillTarget }),
  });
  setFooter(`Removed skills from ${skillTarget}`);
  refreshSkills();
});

el("btn-relay-stop").addEventListener("click", async () => {
  if (!confirm("Stop the AgentRelay background service on this computer?")) return;
  await api("/api/relay/stop", { method: "POST" });
  setFooter("Relay stopping…");
  setRelay(false);
});

for (const id of ["yolo-mode", "yolo-mode-terminals"]) {
  el(id)?.addEventListener("change", (e) => setYoloEnabled(e.target.checked));
}
syncYoloCheckboxes();

async function pollDeliveries() {
  try {
    const r = await fetch(`http://127.0.0.1:${API_PORT}/pending-deliveries`);
    if (!r.ok) return;
    const data = await r.json();
    const items = data.deliveries || [];
    if (!items.length || !window.AgentRelayTerminals?.deliverToAgent) return;
    for (const item of items) {
      const agent = item.adapter_name || item.agent;
      if (!agent || !item.prompt) continue;
      window.AgentRelayTerminals.deliverToAgent(
        agent,
        API_PORT,
        AUTH_TOKEN,
        item.prompt,
        item.wait_seconds || 5,
      );
      setFooter(`Delivered message to ${agent} terminal`);
      showView("terminals");
    }
  } catch {
    /* daemon may be down */
  }
}

// ── Tasks panel ──────────────────────────────────────────────────────────────

const TASK_STATUS = {
  queued:    { label: "queued",    color: "#8b949e" },
  sent:      { label: "sent",      color: "#2f81f7" },
  received:  { label: "received",  color: "#58a6ff" },
  running:   { label: "running",   color: "#d29922" },
  completed: { label: "done",      color: "#3fb950" },
  failed:    { label: "failed",    color: "#f85149" },
};

const TERMINAL_STATUSES = new Set(["completed", "failed"]);

let _taskPollTimer = null;
let _taskEventSource = null;
let _tasksInitialized = false;

function initTasksPanel() {
  if (_tasksInitialized) return;
  _tasksInitialized = true;

  _taskEventSource = new EventSource(`http://127.0.0.1:${API_PORT}/api/tasks/events`);
  _taskEventSource.onmessage = () => {
    clearTimeout(_taskPollTimer);
    fetchTasks();
  };

  fetchTasks();
}

async function fetchTasks() {
  const { ok, data } = await api("/api/tasks?limit=50");
  if (!ok) return;
  renderTasks(data.tasks || []);
  const hasActive = (data.tasks || []).some((t) => !TERMINAL_STATUSES.has(t.status));
  clearTimeout(_taskPollTimer);
  if (hasActive) {
    _taskPollTimer = setTimeout(fetchTasks, 2000);
  }
}

function escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function relTime(ts) {
  const d = Math.round(Date.now() / 1000 - ts);
  if (d < 60) return `${d}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  return `${Math.round(d / 3600)}h ago`;
}

function fmtDuration(secs) {
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
}

function renderTasks(tasks) {
  const tbody = el("tasks-tbody");
  if (!tasks.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="tasks-empty">No tasks yet — send one from an agent using /relay-send or agent-send.</td></tr>';
    return;
  }
  const now = Date.now() / 1000;
  tbody.innerHTML = tasks.map((t) => {
    const cfg = TASK_STATUS[t.status] || { label: t.status, color: "#8b949e" };
    const badge = `<span class="task-badge" style="--task-color:${cfg.color}">${cfg.label}</span>`;
    const duration = TERMINAL_STATUSES.has(t.status)
      ? fmtDuration(t.updated_at - t.created_at)
      : t.status === "running"
        ? fmtDuration(now - t.created_at) + "…"
        : "—";
    const msg = (t.message || "").length > 55
      ? escHtml(t.message.slice(0, 55)) + "…"
      : escHtml(t.message || "");
    const sessionCell = t.session_id
      ? `<a href="#" class="task-attach" data-session="${escHtml(t.session_id)}" data-agent="${escHtml(t.target_agent)}">[attach]</a>`
      : "—";
    return `<tr>
      <td>${badge}</td>
      <td>${escHtml(t.target_node)}</td>
      <td>${escHtml(t.target_agent)}</td>
      <td class="task-msg" title="${escHtml(t.message)}">${msg}</td>
      <td>${relTime(t.created_at)}</td>
      <td>${duration}</td>
      <td>${sessionCell}</td>
    </tr>`;
  }).join("");

  tbody.querySelectorAll(".task-attach").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      showView("terminals");
      window.AgentRelayTerminals?.openTerminal(
        a.dataset.agent, API_PORT, AUTH_TOKEN, { sessionId: a.dataset.session, reuse: false });
    });
  });
}

document.querySelector('.nav-item[data-view="tasks"]')
  ?.addEventListener("click", initTasksPanel);

el("btn-tasks-refresh")?.addEventListener("click", fetchTasks);

refresh();
refreshSkills();
setInterval(refresh, 5000);
setInterval(pollDeliveries, 500);
setInterval(async () => {
  const inbox = await api(`/api/inbox?since=${lastInboxTs}`);
  const messages = inbox.data.messages || [];
  if (messages.length) {
    lastInboxTs = Math.max(...messages.map((m) => m.ts));
    renderInbox(messages);
  }
}, 3000);
