/** AgentRelay local web UI — talks to the embedded daemon on localhost. */

const params = new URLSearchParams(window.location.search);
const AUTH_TOKEN = params.get("token") || sessionStorage.getItem("agentrelay_token") || "";
const API_PORT = parseInt(params.get("port") || "9876", 10);

if (AUTH_TOKEN) {
  sessionStorage.setItem("agentrelay_token", AUTH_TOKEN);
}

const el = (id) => document.getElementById(id);
let sendTargets = [];
let sshHosts = [];
let lastInboxTs = 0;

const YOLO_STORAGE_KEY = "agentrelay_yolo_mode";
const PROFILE_STORAGE_KEY = "agentrelay_launch_profile";

/** Plain-language labels for permission levels (see docs/permission-profiles.md). */
const PROFILE_UI_LABELS = {
  safe: "Careful — asks before risky steps",
  project_write: "Project helper — edits files freely",
  full_auto: "Full auto — no prompts (trusted projects only)",
};

const PROFILE_SHORT = {
  safe: "Careful",
  project_write: "Project",
  full_auto: "Full auto",
};

let profileCatalog = [];

function getLaunchProfile() {
  let p = sessionStorage.getItem(PROFILE_STORAGE_KEY);
  if (!p && sessionStorage.getItem(YOLO_STORAGE_KEY) === "1") {
    p = "full_auto";
    sessionStorage.setItem(PROFILE_STORAGE_KEY, p);
  }
  return p || "safe";
}

function setLaunchProfile(profileId) {
  sessionStorage.setItem(PROFILE_STORAGE_KEY, profileId);
  syncProfileSelects();
  updateProfileHints();
}

function profileFriendly(id) {
  return PROFILE_SHORT[id] || id || "—";
}

function syncProfileSelects() {
  const current = getLaunchProfile();
  for (const id of ["launch-profile", "launch-profile-terminals", "send-profile"]) {
    const sel = el(id);
    if (sel) sel.value = current;
  }
}

function updateProfileHints() {
  const p = getLaunchProfile();
  const text = p === "full_auto"
    ? "The agent can act without asking. Use only on projects you fully trust."
    : p === "project_write"
      ? "The agent can change project files more freely; shell commands may still ask."
      : "The agent asks before risky actions (recommended default).";
  for (const id of ["profile-hint-agents", "profile-hint-terminals"]) {
    const hint = el(id);
    if (hint) hint.textContent = text;
  }
}

async function loadPermissionProfiles() {
  const { ok, data } = await api("/api/profiles");
  if (!ok) return;
  profileCatalog = data.profiles || [];
  for (const selectId of ["launch-profile", "launch-profile-terminals", "send-profile"]) {
    const sel = el(selectId);
    if (!sel) continue;
    sel.innerHTML = "";
    for (const p of profileCatalog) {
      const opt = document.createElement("option");
      opt.value = p.id;
      const short = selectId === "launch-profile-terminals" && PROFILE_SHORT[p.id];
      opt.textContent = short || PROFILE_UI_LABELS[p.id] || p.label || p.id;
      sel.appendChild(opt);
    }
  }
  syncProfileSelects();
  updateProfileHints();
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
  // Use relative path if we are on the same host, otherwise use hardcoded 127.0.0.1
  const baseUrl = window.location.origin.includes("127.0.0.1") || window.location.origin.includes("localhost")
    ? ""
    : `http://127.0.0.1:${API_PORT}`;

  const url = path.startsWith("http") ? path : `${baseUrl}${path}`;
  const r = await fetch(url, { ...opts, headers });
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
window.showView = showView;

function setRelay(on) {
  el("status-badge").textContent = on ? "Running" : "Stopped";
  el("status-badge").className = on ? "badge on" : "badge off";
}

function relayContent(content) {
  el("send-message").value = content;
  showView("agents");
  el("send-message").focus();
  el("send-message").scrollIntoView({ behavior: 'smooth', block: 'center' });
  setFooter("Content copied to send form");
}

function renderAgents(agents, agentsMissing) {
  const ul = el("local-agents");
  const launch = el("launch-agent");
  const termAgent = el("terminal-agent");
  const prevLaunch = launch.value;
  const prevTermAgent = termAgent.value;
  ul.innerHTML = "";
  launch.innerHTML = "";
  termAgent.innerHTML = "";
  agents = agents || [];
  agentsMissing = agentsMissing || [];

  if (!agents.length && !agentsMissing.length) {
    ul.innerHTML = "<li>No agents configured</li>";
    return;
  }

  for (const a of agents) {
    const li = document.createElement("li");
    li.className = "agent-card";
    const style = window.AgentRelayColors?.applyAgentColor(li, a.id) || {};
    const kind = a.mode === "visible" ? "Interactive" : "Background";
    const extra = a.role ? ` · ${a.role}` : "";
    li.innerHTML = `
      <div class="agent-card-head">
        <span class="agent-swatch" style="background:${style.color}"></span>
        <strong class="agent-name">${a.label || a.id}</strong>
      </div>
      <span class="hint">${kind}${extra} · ready</span>`;
    ul.appendChild(li);

    for (const select of [launch, termAgent]) {
      const opt = document.createElement("option");
      opt.value = a.id;
      opt.textContent = a.label || a.id;
      select.appendChild(opt);
    }
  }

  for (const a of agentsMissing) {
    const li = document.createElement("li");
    li.className = "agent-card agent-card-missing";
    const style = window.AgentRelayColors?.applyAgentColor(li, a.id) || {};
    const kind = a.mode === "visible" ? "Interactive" : "Background";
    const reason = a.reason || "not on PATH";
    li.innerHTML = `
      <div class="agent-card-head">
        <span class="agent-swatch" style="background:${style.color}"></span>
        <strong class="agent-name">${a.label || a.id}</strong>
      </div>
      <span class="hint">${kind} · not installed (${reason})</span>`;
    li.style.opacity = "0.65";
    ul.appendChild(li);
  }

  if ([...launch.options].some((o) => o.value === prevLaunch)) launch.value = prevLaunch;
  if ([...termAgent.options].some((o) => o.value === prevTermAgent)) termAgent.value = prevTermAgent;
  loadResumeSessions("agents-resume-session", launch.value);
  loadResumeSessions("terminal-resume-session", termAgent.value);
}

async function loadResumeSessions(selectId, agent) {
  const sel = el(selectId);
  if (!sel || !agent) return;
  const prev = sel.value;
  sel.innerHTML = "<option value=\"\">No session (fresh start)</option>";
  try {
    const { ok, data } = await api(`/api/sessions/${encodeURIComponent(agent)}`);
    if (ok && data.sessions && data.sessions.length) {
      for (const s of data.sessions) {
        const opt = document.createElement("option");
        opt.value = s.sessionId;
        const cwd = s.cwd ? s.cwd.replace(/.*\//, "") || s.cwd : "";
        const date = s.startedAt ? new Date(s.startedAt).toLocaleString() : s.procStart;
        opt.textContent = `${date}${cwd ? " · " + cwd : ""}`;
        sel.appendChild(opt);
      }
      if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
    }
  } catch { /* ignore */ }
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
    const running = parseAgentCsv(p.active_agents);
    const installed = installedAgentsFromPeer(p);
    let meta = "Agent relay";
    if (running.length) {
      meta = `Running: ${running.join(", ")}`;
    } else if (installed.length) {
      meta = `Installed: ${installed.join(", ")}`;
    }
    li.innerHTML = `
      <div class="peer-row">
        <div>
          <div class="peer-name">${p.name}</div>
          <div class="peer-meta">${meta}</div>
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

function parseAgentCsv(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  return String(value || "").split(",").map((a) => a.trim()).filter(Boolean);
}

function agentListFromPeer(peer) {
  const active = parseAgentCsv(peer.active_agents);
  if (active.length) return active;
  return parseAgentCsv(peer.agents);
}

function installedAgentsFromPeer(peer) {
  return parseAgentCsv(peer.agents);
}

function renderSendTargets(data) {
  const targetSelect = el("send-target");
  const localAgents = (data.agents || []).map((a) => a.id).filter(Boolean);
  const localActive = parseAgentCsv(data.active_agents);
  sendTargets = [{
    name: `This computer (${data.node || "local"})`,
    address: "127.0.0.1",
    port: data.port || API_PORT,
    agents: localActive.length ? localActive : localAgents,
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
  const previous = agentSelect.value;
  agentSelect.innerHTML = "";
  for (const agent of agents) {
    const option = document.createElement("option");
    option.value = agent;
    option.textContent = agent;
    agentSelect.appendChild(option);
  }
  if (agents.includes(previous)) {
    agentSelect.value = previous;
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
    log.innerHTML = '<div class="hint" style="padding:1rem">(no messages yet)</div>';
    return;
  }
  log.innerHTML = "";
  for (const m of messages) {
    const item = document.createElement("div");
    item.className = "inbox-item";
    item.style.marginBottom = "1.5rem";
    item.style.padding = "0.75rem";
    item.style.borderBottom = "1px solid var(--border)";
    
    const header = document.createElement("div");
    header.style.display = "flex";
    header.style.justifyContent = "space-between";
    header.style.alignItems = "center";
    header.style.marginBottom = "0.5rem";
    
    const meta = document.createElement("span");
    meta.style.fontSize = "0.8rem";
    meta.style.color = "var(--muted)";
    meta.textContent = `[${new Date(m.ts * 1000).toLocaleTimeString()}] ${m.from} → ${m.agent || "?"}`;
    
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn ghost small";
    btn.textContent = "Relay to...";
    btn.addEventListener("click", () => relayContent(m.command));
    
    header.appendChild(meta);
    header.appendChild(btn);
    
    const body = document.createElement("div");
    body.style.whiteSpace = "pre-wrap";
    body.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, monospace";
    body.style.fontSize = "0.85rem";
    body.textContent = m.command;
    
    item.appendChild(header);
    item.appendChild(body);
    log.appendChild(item);
  }
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
  renderAgents(data.agents || [], data.agents_missing || []);
  renderNearby(data.nearby || []);
  renderSendTargets(data);

  if (!data.agents?.length && data.agents_missing?.length) {
    const names = data.agents_missing.map((a) => a.executable || a.id).join(", ");
    setFooter(`No agent CLIs on PATH. Install: ${names}`);
  } else if (data.agents_missing?.length) {
    const names = data.agents_missing.map((a) => a.label || a.id).join(", ");
    setFooter(`${data.agents.length} agent(s) ready; not installed: ${names}`);
  }

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

  refreshSSH();
  refreshCoordAgents(data);
}

async function refreshSSH() {
  const { ok, data } = await api("/api/ssh-hosts");
  if (!ok) return;
  sshHosts = data.hosts || [];
  renderSSHHosts(sshHosts);
  renderSSHTerminalChoices(sshHosts);

  const pending = await api("/api/ssh-hosts/pending-presets");
  renderSSHPending(pending.data.pending || []);
}

function renderSSHTerminalChoices(hosts) {
  const sel = el("terminal-ssh-host");
  const btn = el("btn-new-ssh-terminal");
  if (!sel || !btn) return;
  sel.innerHTML = "";
  if (!hosts.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No SSH connections";
    sel.appendChild(opt);
    sel.disabled = true;
    btn.disabled = true;
    return;
  }
  sel.disabled = false;
  btn.disabled = false;
  for (const h of hosts) {
    const opt = document.createElement("option");
    opt.value = h.node_name;
    opt.textContent = `${h.node_name} (${h.user}@${h.host})`;
    sel.appendChild(opt);
  }
}

function renderSSHHosts(hosts) {
  const ul = el("ssh-hosts-list");
  ul.innerHTML = "";
  if (!hosts.length) {
    ul.innerHTML = '<li class="empty">No SSH presets yet.</li>';
    return;
  }
  for (const h of hosts) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="peer-row">
        <div>
          <div class="peer-name">${h.node_name}</div>
          <div class="peer-meta">${h.user}@${h.host}:${h.port}</div>
        </div>
        <div class="row">
          <button type="button" class="btn ghost small btn-ssh-shell" data-node="${h.node_name}">Shell</button>
          <button type="button" class="btn ghost small btn-ssh-test" data-node="${h.node_name}">Test</button>
          <button type="button" class="btn ghost small btn-ssh-delete" data-node="${h.node_name}">Delete</button>
        </div>
      </div>`;
    ul.appendChild(li);
  }
  ul.querySelectorAll(".btn-ssh-shell").forEach(btn => {
    btn.addEventListener("click", () => openSshTerminal(btn.dataset.node));
  });
  ul.querySelectorAll(".btn-ssh-test").forEach(btn => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Testing...";
      const { ok, data } = await api(`/api/ssh-hosts/${btn.dataset.node}/test`, { method: "POST" });
      btn.disabled = false;
      btn.textContent = "Test";
      setFooter(ok ? `SSH Success: ${data.message}` : `SSH Failed: ${data.error || data.message}`);
    });
  });
  ul.querySelectorAll(".btn-ssh-delete").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Delete SSH preset for ${btn.dataset.node}?`)) return;
      await api(`/api/ssh-hosts/${btn.dataset.node}`, { method: "DELETE" });
      refreshSSH();
    });
  });
}

function renderSSHPending(pending) {
  const card = el("ssh-pending-card");
  const ul = el("ssh-pending-list");
  if (!pending || !pending.length) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  ul.innerHTML = "";
  for (const p of pending) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="peer-row">
        <span>${p.type === "rename" ? `<strong>${p.old_node_name}</strong> renamed to <strong>${p.new_node_name}</strong>` : `New peer <strong>${p.node_name}</strong> discovered`}</span>
        <button type="button" class="btn primary small btn-ssh-apply" data-raw='${JSON.stringify(p)}'>Apply</button>
      </div>`;
    ul.appendChild(li);
  }
  ul.querySelectorAll(".btn-ssh-apply").forEach(btn => {
    btn.addEventListener("click", () => {
      const p = JSON.parse(btn.dataset.raw);
      el("ssh-node").value = p.new_node_name || p.node_name;
      el("ssh-host").value = p.host;
      el("ssh-user").value = "";
      el("ssh-form-card").hidden = false;
    });
  });
}

function refreshCoordAgents(data) {
  if (!data) return;

  const list = el("coord-agents-list");
  const synthSelect = el("coord-synthesizer");

  // Keep track of which ones were checked
  const checked = new Set();
  list.querySelectorAll("input:checked").forEach(i => checked.add(i.value));
  const prevSynth = synthSelect.value;

  list.innerHTML = "";
  synthSelect.innerHTML = '<option value="">None (Broadcast only)</option>';

  const allAgents = [];
  // Local agents
  for (const a of data.agents || []) {
    allAgents.push({ node: data.node, agent: a.id, label: `${a.id}@${data.node}` });
  }
  // Remote agents
  for (const p of data.nearby || []) {
    if (!p.connected) continue;
    const pAgents = agentListFromPeer(p);
    for (const a of pAgents) {
      allAgents.push({ node: p.name, agent: a, label: `${a}@${p.name}` });
    }
  }

  for (const item of allAgents) {
    const val = `${item.agent}@${item.node}`;
    const div = document.createElement("div");
    div.className = "coord-agent-item";
    window.AgentRelayColors?.applyAgentColor(div, item.agent);
    const isChecked = checked.has(val) ? "checked" : "";
    div.innerHTML = `<label><input type="checkbox" value="${val}" ${isChecked}> <span class="agent-swatch"></span> ${item.label}</label>`;
    list.appendChild(div);

    if (item.node === data.node) {
      const opt = document.createElement("option");
      opt.value = item.agent;
      opt.textContent = item.label;
      synthSelect.appendChild(opt);
    }
  }
  synthSelect.value = prevSynth;
}

el("btn-add-ssh").addEventListener("click", () => {
  el("ssh-form-card").hidden = false;
});

el("btn-ssh-cancel").addEventListener("click", () => {
  el("ssh-form-card").hidden = true;
});

el("btn-ssh-save").addEventListener("click", async () => {
  const btn = el("btn-ssh-save");
  btn.disabled = true;
  btn.textContent = "Testing...";
  const payload = {
    node_name: el("ssh-node").value.trim(),
    host: el("ssh-host").value.trim(),
    user: el("ssh-user").value.trim(),
    port: parseInt(el("ssh-port").value, 10) || 22,
    key_path: el("ssh-key").value.trim(),
  };
  const { ok, data } = await api("/api/ssh-hosts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  btn.disabled = false;
  btn.textContent = "Test & Save";
  if (!ok) {
    setFooter(data.error || data.message || "Failed to save SSH host");
    return;
  }
  el("ssh-form-card").hidden = true;
  refreshSSH();
});

el("btn-coord-run").addEventListener("click", async () => {
  const btn = el("btn-coord-run");
  const task = el("coord-task").value.trim();
  const selected = Array.from(el("coord-agents-list").querySelectorAll("input:checked")).map(i => {
    const [agent, node] = i.value.split("@");
    return { agent, node };
  });

  if (!task || !selected.length) {
    el("coord-status").textContent = "Select agents and enter a task.";
    return;
  }

  btn.disabled = true;
  el("coord-status").textContent = "Coordinating...";
  el("coord-results-card").hidden = true;

  const coordinator_agent = el("coord-synthesizer").value || null;

  const { ok, data } = await api("/api/coordinate", {
    method: "POST",
    body: JSON.stringify({
      task,
      agents: selected,
      mode: el("coord-mode").value,
      coordinator_agent,
    }),
  });

  btn.disabled = false;
  if (!ok) {
    el("coord-status").textContent = data.error || "Coordination failed.";
    return;
  }

  el("coord-status").textContent = "Coordination complete.";
  el("coord-results-card").hidden = false;

  if (data.synthesis) {
    el("coord-synthesis-wrap").hidden = false;
    const synthWrap = el("coord-synthesis");
    synthWrap.innerHTML = "";
    
    const synthPre = document.createElement("div");
    synthPre.style.whiteSpace = "pre-wrap";
    synthPre.textContent = data.synthesis;
    
    const synthBtn = document.createElement("button");
    synthBtn.type = "button";
    synthBtn.className = "btn ghost small";
    synthBtn.style.marginTop = "0.5rem";
    synthBtn.textContent = "Relay synthesis...";
    synthBtn.addEventListener("click", () => relayContent(data.synthesis));
    
    synthWrap.appendChild(synthPre);
    synthWrap.appendChild(synthBtn);
  } else {
    el("coord-synthesis-wrap").hidden = true;
  }

  const resList = el("coord-results-list");
  resList.innerHTML = "";
  for (const res of data.agent_results || []) {
    const item = document.createElement("div");
    item.className = "coord-result-item";
    const status = res.error ? `<span style="color:var(--muted)">Error: ${res.error}</span>` : `OK (exit ${res.exit_code})`;
    item.innerHTML = `
      <div class="coord-result-header">
        <span class="coord-result-agent">${res.agent}@${res.node}</span>
        <span class="coord-result-meta">${status}</span>
      </div>
      <div class="snippet" style="position:relative">
        <div class="coord-result-body" style="white-space:pre-wrap">${escHtml(res.content || "(no response)")}</div>
        <button type="button" class="btn ghost small btn-relay-coord" style="margin-top:0.5rem">Relay response</button>
      </div>
    `;
    item.querySelector(".btn-relay-coord").addEventListener("click", () => relayContent(res.content));
    resList.appendChild(item);
  }
});

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

el("btn-send-snippet-terminal").addEventListener("click", () => {
  const snip = el("agent-snippet").textContent;
  if (!snip) {
    setFooter("No agent instructions loaded");
    return;
  }
  const sent = window.AgentRelayTerminals?.sendToActiveTerminal(snip);
  setFooter(sent
    ? "Sent AgentRelay instructions to active terminal"
    : "Open a live terminal tab first");
  if (sent) showView("terminals");
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
      permission_profile: el("send-profile")?.value || getLaunchProfile(),
    }),
  });
  el("send-status").textContent = ok
    ? (data.stdout || data.message || "Sent.")
    : (data.error || data.stderr || "Send failed.");
  if (ok) el("send-message").value = "";
});

el("btn-clear-send").addEventListener("click", () => {
  el("send-message").value = "";
  el("send-status").textContent = "";
});
function openAgentTerminal(agent, { injectSnippet = false, reuse = false, onOpen = null, resumeSessionId = null } = {}) {
  if (!agent) return;
  showView("terminals");
  const profile = getLaunchProfile();
  window.AgentRelayTerminals.openTerminal(agent, API_PORT, AUTH_TOKEN, {
    injectSnippet,
    reuse,
    profile,
    yolo: profile === "full_auto",
    onOpen,
    resumeSessionId,
  });
}

function openSshTerminal(nodeName, { reuse = false, onOpen = null } = {}) {
  if (!nodeName) return;
  showView("terminals");
  window.AgentRelayTerminals.openSshTerminal(nodeName, API_PORT, AUTH_TOKEN, {
    reuse,
    onOpen,
  });
}

el("terminal-agent").addEventListener("change", () => {
  loadResumeSessions("terminal-resume-session", el("terminal-agent").value);
});

el("launch-agent").addEventListener("change", () => {
  loadResumeSessions("agents-resume-session", el("launch-agent").value);
});

el("btn-new-terminal").addEventListener("click", () => {
  const agent = el("terminal-agent").value;
  if (!agent) return;
  try {
    const resumeSessionId = el("terminal-resume-session").value || null;
    openAgentTerminal(agent, { injectSnippet: false, reuse: false, resumeSessionId });
    setFooter(resumeSessionId ? `Resuming session for ${agent}` : `New terminal for ${agent}`);
  } catch (e) {
    setFooter(`Terminal error: ${e.message}`);
  }
});

el("btn-new-ssh-terminal").addEventListener("click", () => {
  const nodeName = el("terminal-ssh-host").value;
  if (!nodeName) {
    setFooter("Save an SSH connection first");
    return;
  }
  try {
    openSshTerminal(nodeName);
    setFooter(`Opening SSH shell for ${nodeName}`);
  } catch (e) {
    setFooter(`SSH terminal error: ${e.message}`);
  }
});

function closeTerminalActionsMenu() {
  const menu = el("terminal-actions-menu");
  if (menu) menu.open = false;
}

el("btn-relay-selection").addEventListener("click", () => {
  const selection = window.AgentRelayTerminals?.getActiveSelection();
  if (!selection) {
    setFooter("No text selected in terminal");
    closeTerminalActionsMenu();
    return;
  }
  relayContent(selection);
  closeTerminalActionsMenu();
});

el("btn-clear-terminal").addEventListener("click", () => {
  window.AgentRelayTerminals?.clearActiveTerminal();
  closeTerminalActionsMenu();
});

el("btn-launch-agent").addEventListener("click", async () => {
  const agent = el("launch-agent").value;
  if (!agent) return;
  try {
    openAgentTerminal(agent, {
      injectSnippet: true,
      reuse: true,
      onOpen: (frame) => {
        setFooter(frame.new_session
          ? `Launched ${agent} — AgentRelay instructions sent to terminal`
          : `Reattached to ${agent} — existing session left unchanged`);
      },
    });
    const snip = el("agent-snippet").textContent;
    if (snip) {
      try {
        await navigator.clipboard.writeText(snip);
      } catch {
        /* clipboard optional */
      }
    }
    setFooter(`Opening ${agent} terminal`);
  } catch (e) {
    setFooter(`Launch error: ${e.message}`);
  }
});

el("btn-open-terminal").addEventListener("click", () => {
  const agent = el("launch-agent").value;
  if (!agent) return;
  try {
    const resumeSessionId = el("agents-resume-session").value || null;
    openAgentTerminal(agent, { injectSnippet: false, reuse: false, resumeSessionId });
    setFooter(resumeSessionId ? `Resuming session for ${agent}` : `Opened fresh terminal for ${agent}`);
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

for (const id of ["launch-profile", "launch-profile-terminals", "send-profile"]) {
  el(id)?.addEventListener("change", (e) => setLaunchProfile(e.target.value));
}
loadPermissionProfiles();

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

async function pollWorkQueue() {
  try {
    const { ok, data } = await api("/api/work-queue/tick", { method: "POST" });
    if (!ok || !data?.dispatched || !data.needs_terminal) return;
    if (!window.AgentRelayTerminals?.deliverToAgent) return;
    const agent = data.agent;
    const prompt = data.prompt;
    if (!agent || !prompt) return;
    const workMeta = data.kind && data.id ? { kind: data.kind, id: data.id } : null;
    window.AgentRelayTerminals.deliverToAgent(
      agent,
      API_PORT,
      AUTH_TOKEN,
      prompt,
      data.wait_seconds || 5,
      workMeta,
    );
    const label = data.kind === "bug" ? "bug" : "idea";
    setFooter(`Auto-run: opened ${agent} for queued ${label}`);
    showView("terminals");
    if (window.ideasLoad) window.ideasLoad();
    if (window.bugsLoad) window.bugsLoad();
  } catch {
    /* daemon may be down */
  }
}

// ── Threads view ─────────────────────────────────────────────────────────────

async function refreshThreads() {
  const { ok, data } = await api("/talk/threads");
  if (!ok) return;
  renderThreads(data.threads || []);
}

function renderThreads(threads) {
  const ul = el("threads-list");
  ul.innerHTML = "";
  if (!threads.length) {
    ul.innerHTML = '<li class="empty">No conversations yet.</li>';
    return;
  }
  for (const t of threads) {
    const li = document.createElement("li");
    li.style.cursor = "pointer";
    li.style.borderRadius = "0";
    li.style.border = "none";
    li.style.borderBottom = "1px solid var(--border)";
    li.innerHTML = `
      <div style="font-weight:600; font-size:0.85rem;">${t.local_agent} ↔ ${t.remote_agent}</div>
      <div class="hint" style="font-size:0.75rem;">${t.remote_node} · ${relTime(t.updated)}</div>
    `;
    li.addEventListener("click", () => showThread(t));
    ul.appendChild(li);
  }
}

async function showThread(t) {
  el("thread-title").textContent = `${t.local_agent} on this machine ↔ ${t.remote_agent} on ${t.remote_node}`;
  const { ok, data } = await api(`/talk/threads/${t.id}`);
  if (!ok) return;

  const container = el("thread-messages");
  container.innerHTML = "";
  for (const m of data.messages || []) {
    const div = document.createElement("div");
    div.style.marginBottom = "1rem";
    div.style.padding = "0.75rem";
    div.style.borderRadius = "8px";
    div.style.background = m.role === "assistant" ? "rgba(47, 129, 247, 0.1)" : "rgba(255, 255, 255, 0.05)";
    div.style.border = "1px solid var(--border)";
    
    const header = document.createElement("div");
    header.style.display = "flex";
    header.style.justifyContent = "space-between";
    header.style.alignItems = "center";
    header.style.marginBottom = "0.5rem";
    
    const meta = document.createElement("span");
    meta.style.fontSize = "0.75rem";
    meta.style.color = "var(--muted)";
    meta.textContent = `[${new Date(m.ts * 1000).toLocaleTimeString()}] ${m.from_agent}@${m.from_node}:`;
    
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn ghost small";
    btn.textContent = "Relay";
    btn.addEventListener("click", () => relayContent(m.content));
    
    header.appendChild(meta);
    header.appendChild(btn);
    
    const body = document.createElement("div");
    body.style.whiteSpace = "pre-wrap";
    body.style.fontSize = "0.85rem";
    body.textContent = m.content;
    
    div.appendChild(header);
    div.appendChild(body);
    container.appendChild(div);
  }
  container.scrollTop = container.scrollHeight;
}

document.querySelector('.nav-item[data-view="threads"]')?.addEventListener("click", refreshThreads);
el("btn-threads-refresh")?.addEventListener("click", refreshThreads);

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

function apiAgentPath(agent) {
  return encodeURIComponent(agent);
}

function renderSafeMarkdown(markdown) {
  const html = marked.parse(escHtml(markdown));
  const template = document.createElement("template");
  template.innerHTML = html;
  template.content.querySelectorAll("script, style, iframe, object, embed").forEach((node) => node.remove());
  template.content.querySelectorAll("*").forEach((node) => {
    for (const attr of Array.from(node.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value.trim().toLowerCase();
      if (name.startsWith("on")) {
        node.removeAttribute(attr.name);
      } else if ((name === "href" || name === "src") && value.startsWith("javascript:")) {
        node.removeAttribute(attr.name);
      }
    }
  });
  return template.innerHTML;
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
    tbody.innerHTML = '<tr><td colspan="8" class="tasks-empty">Nothing here yet — send work from an agent or from the Agents screen.</td></tr>';
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
      ? `<a href="#" class="task-attach" data-session="${escHtml(t.session_id)}" data-agent="${escHtml(t.target_agent)}" data-node="${escHtml(t.target_node)}">Open</a>`
      : "—";
    const freedom = profileFriendly(t.permission_profile);
    return `<tr>
      <td>${badge}</td>
      <td>${escHtml(t.target_node)}</td>
      <td>${escHtml(t.target_agent)}</td>
      <td>${escHtml(freedom)}</td>
      <td class="task-msg" title="${escHtml(t.message)}">${msg}</td>
      <td>${relTime(t.created_at)}</td>
      <td>${duration}</td>
      <td>${sessionCell}</td>
    </tr>`;
  }).join("");

  tbody.querySelectorAll(".task-attach").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const targetNode = a.dataset.node;
      const localNode = el("node-name").value;
      let host = "127.0.0.1";
      let port = API_PORT;
      if (targetNode && targetNode !== localNode) {
        const peer = sendTargets.find((t) => t.name === targetNode);
        if (!peer) {
          setFooter(`Peer ${targetNode} is not currently connected`);
          return;
        }
        host = peer.address;
        port = peer.port;
      }
      showView("terminals");
      window.AgentRelayTerminals?.openTerminal(
        a.dataset.agent, port, AUTH_TOKEN,
        { sessionId: a.dataset.session, reuse: false, host });
    });
  });
}

document.querySelector('.nav-item[data-view="tasks"]')
  ?.addEventListener("click", initTasksPanel);

el("btn-tasks-refresh")?.addEventListener("click", fetchTasks);

// ── Resumes & Memory ────────────────────────────────────────────────────────

let selectedResumeAgent = null;

async function refreshResumes() {
  const { ok, data } = await api("/api/status");
  if (!ok) return;
  const list = el("resumes-agent-list");
  list.innerHTML = "";
  const agents = (data.agents || []).map(a => a.id);
  if (!agents.length) {
    list.innerHTML = '<li class="empty" style="padding:1rem">No local agents found</li>';
    return;
  }
  for (const agent of agents) {
    const li = document.createElement("li");
    li.className = selectedResumeAgent === agent ? "active agent-card" : "agent-card";
    window.AgentRelayColors?.applyAgentColor(li, agent);
    li.innerHTML = `<span class="agent-swatch"></span> <span class="agent-name">${agent}</span>`;
    li.style.cursor = "pointer";
    li.style.borderRadius = "0";
    li.style.border = "none";
    li.style.borderBottom = "1px solid var(--border)";
    li.addEventListener("click", () => showResume(agent));
    list.appendChild(li);
  }
}

async function showResume(agent) {
  selectedResumeAgent = agent;
  const agentPath = apiAgentPath(agent);
  const { ok: rOk, data: rData } = await api(`/api/agents/${agentPath}/resume`);
  const { ok: mOk, data: mData } = await api(`/api/agents/${agentPath}/memory`);

  el("resume-agent-name").textContent = agent;
  el("btn-edit-resume").hidden = false;
  el("resume-display").hidden = false;
  el("resume-editor-wrap").hidden = true;
  el("memory-card").hidden = false;

  if (rOk) {
    el("resume-display").innerHTML = renderSafeMarkdown(rData.resume);
    el("resume-editor").value = rData.resume;
  }

  renderMemory(mOk ? mData.memory || {} : {});
  refreshResumes(); // Update active class
}

function renderMemory(memory) {
  const container = el("memory-display");
  container.innerHTML = "";
  const keys = Object.keys(memory);
  if (!keys.length) {
    container.innerHTML = '<p class="hint">No facts remembered yet.</p>';
    return;
  }
  for (const k of keys) {
    const div = document.createElement("div");
    div.className = "memory-fact";
    div.innerHTML = `
      <span class="memory-key">${escHtml(k)}</span>
      <span class="memory-val">${escHtml(memory[k])}</span>
      <button type="button" class="btn ghost small btn-del-mem" style="padding:0 0.4rem" data-key="${escHtml(k)}">&times;</button>
    `;
    div.querySelector(".btn-del-mem").addEventListener("click", () => deleteMemoryFact(k));
    container.appendChild(div);
  }
}

async function saveResume() {
  const content = el("resume-editor").value;
  const { ok } = await api(`/api/agents/${apiAgentPath(selectedResumeAgent)}/resume`, {
    method: "POST",
    body: JSON.stringify({ resume: content })
  });
  if (ok) {
    showResume(selectedResumeAgent);
    setFooter(`Resume saved for ${selectedResumeAgent}`);
  }
}

async function addMemoryFact() {
  if (!selectedResumeAgent) return;
  const k = el("memory-key").value.trim();
  const v = el("memory-val").value.trim();
  if (!k || !v) return;

  const { ok, data } = await api(`/api/agents/${apiAgentPath(selectedResumeAgent)}/memory`);
  if (!ok) return;
  const mem = data.memory || {};
  mem[k] = v;

  const { ok: sOk } = await api(`/api/agents/${apiAgentPath(selectedResumeAgent)}/memory`, {
    method: "POST",
    body: JSON.stringify({ memory: mem })
  });
  if (sOk) {
    el("memory-key").value = "";
    el("memory-val").value = "";
    showResume(selectedResumeAgent);
    setFooter("Fact added to memory");
  }
}

async function deleteMemoryFact(key) {
  const { ok, data } = await api(`/api/agents/${apiAgentPath(selectedResumeAgent)}/memory`);
  if (!ok) return;
  const mem = data.memory || {};
  delete mem[key];

  const { ok: sOk } = await api(`/api/agents/${apiAgentPath(selectedResumeAgent)}/memory`, {
    method: "POST",
    body: JSON.stringify({ memory: mem })
  });
  if (sOk) {
    showResume(selectedResumeAgent);
    setFooter("Fact removed from memory");
  }
}

el("btn-resumes-refresh")?.addEventListener("click", refreshResumes);
el("btn-edit-resume")?.addEventListener("click", () => {
  el("resume-display").hidden = true;
  el("resume-editor-wrap").hidden = false;
  el("btn-edit-resume").hidden = true;
});
el("btn-cancel-resume")?.addEventListener("click", () => {
  el("resume-display").hidden = false;
  el("resume-editor-wrap").hidden = true;
  el("btn-edit-resume").hidden = false;
});
el("btn-save-resume")?.addEventListener("click", saveResume);
el("btn-add-memory")?.addEventListener("click", addMemoryFact);

document.querySelector('.nav-item[data-view="resumes"]')?.addEventListener("click", refreshResumes);

refresh();
refreshSkills();
setInterval(refresh, 5000);
setInterval(pollDeliveries, 500);
setInterval(pollWorkQueue, 5000);
setInterval(async () => {
  const inbox = await api(`/api/inbox?since=${lastInboxTs}`);
  const messages = inbox.data.messages || [];
  if (messages.length) {
    lastInboxTs = Math.max(...messages.map((m) => m.ts));
    renderInbox(messages);
  }
}, 3000);

el("btn-get-latest")?.addEventListener("click", async () => {
  const btn = el("btn-get-latest");
  const status = el("update-status");
  btn.disabled = true;
  btn.textContent = "Checking…";
  status.textContent = "";
  const { ok, data } = await api("/api/update/pull", { method: "POST" });
  btn.disabled = false;
  btn.textContent = "Get latest files";
  if (!ok) {
    status.textContent = data.error || "Could not check for updates.";
    return;
  }
  status.textContent = data.message || (data.already_current ? "Already up to date." : "Updated.");
  setFooter(data.message || "");
});
