async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  return { ok: r.ok, data: await r.json().catch(() => ({})) };
}

const el = (id) => document.getElementById(id);
let relayOn = false;

function setRelay(on) {
  relayOn = on;
  el("status-badge").textContent = on ? "Running" : "Stopped";
  el("status-badge").className = on ? "badge on" : "badge off";
  el("btn-relay").textContent = on ? "Stop" : "Start";
}

function renderAgents(agents) {
  const ul = el("local-agents");
  ul.innerHTML = "";
  if (!agents.length) {
    ul.innerHTML = "<li>No agents configured</li>";
    return;
  }
  for (const a of agents) {
    const li = document.createElement("li");
    const kind = a.mode === "visible" ? "Shows requests in its window" : "Runs in the background";
    li.innerHTML = `<strong>${a.label}</strong><br><span class="hint">${kind}</span>`;
    ul.appendChild(li);
  }
}

function renderNearby(list) {
  const ul = el("nearby-list");
  ul.innerHTML = "";
  if (!list.length) {
    ul.innerHTML = '<li class="empty">No other computers found yet. Make sure AgentRelay is running on them too.</li>';
    return;
  }
  for (const p of list) {
    const li = document.createElement("li");
    const agents = p.agents ? p.agents.replace(/,/g, ", ") : "Agent relay";
    li.innerHTML = `
      <div class="peer-row">
        <div>
          <div class="peer-name">${p.name}</div>
          <div class="peer-meta">${agents}</div>
        </div>
        <div>
          ${p.connected ? '<span class="connected">Connected</span>' : `<button type="button" class="btn primary btn-connect" data-peer="${p.name}">Connect</button>`}
        </div>
      </div>
    `;
    ul.appendChild(li);
  }
  ul.querySelectorAll(".btn-connect").forEach((btn) => {
    btn.addEventListener("click", () => connect(btn.dataset.peer, btn));
  });
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
      <button type="button" class="btn primary" data-id="${p.id}" data-peer="${p.from_node}">Allow</button>
    `;
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

async function refresh() {
  const { data } = await api("/api/status");
  setRelay(data.relay_running);
  el("node-name").value = data.node || "";
  el("this-address").textContent = data.address
    ? `On your network at ${data.address}`
    : "";
  el("wait-seconds").value = data.wait_before_send_seconds || 5;
  renderAgents(data.agents || []);
  renderNearby(data.nearby || []);
  const pending = await api("/api/pending");
  renderPending(pending.data.pending || []);
  const snip = await api("/api/agent-snippet");
  el("agent-snippet").textContent = snip.data.snippet || "";
}

async function connect(peer, btn) {
  btn.disabled = true;
  btn.textContent = "Connecting…";
  const { ok, data } = await api("/api/connect", {
    method: "POST",
    body: JSON.stringify({ peer }),
  });
  if (!ok) {
    alert(data.error || "Could not connect. Approve the request on the other computer.");
    btn.disabled = false;
    btn.textContent = "Connect";
    return;
  }
  refresh();
}

el("btn-relay").addEventListener("click", async () => {
  el("btn-relay").disabled = true;
  await api(relayOn ? "/api/relay/stop" : "/api/relay/start", { method: "POST" });
  el("btn-relay").disabled = false;
  refresh();
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
  refresh();
});

el("btn-copy").addEventListener("click", () => {
  navigator.clipboard.writeText(el("agent-snippet").textContent);
  el("btn-copy").textContent = "Copied!";
  setTimeout(() => { el("btn-copy").textContent = "Copy"; }, 2000);
});

refresh();
setInterval(refresh, 5000);
