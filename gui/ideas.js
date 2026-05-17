/* Ideas panel — brainstorm, concept, and execution workflow */

(function () {
  "use strict";

  const PRIORITY_LABEL = { high: "High", medium: "Med", low: "Low" };
  const PRIORITY_CLASS = { high: "priority-high", medium: "priority-med", low: "priority-low" };
  const STATUS_LABEL = {
    draft: "Draft",
    exploring: "Exploring",
    ready: "Ready",
    concept: "Concept",
    queued: "Queued",
    in_progress: "In progress",
    done: "Done",
  };
  const STATUS_CLASS = {
    draft: "status-draft",
    exploring: "status-inprogress",
    ready: "status-queued",
    concept: "status-queued",
    queued: "status-queued",
    in_progress: "status-inprogress",
    done: "status-done",
  };

  let _ideas = [];
  let _agents = [];
  let _activeAgents = [];
  let _filter = "all";
  let _selectedId = null;
  let _editing = false;
  let _busy = false;
  let _capturedImageData = null;

  function el(id) { return document.getElementById(id); }
  const ideasList = () => el("ideas-list");
  const formPanel = () => el("ideas-form-panel");
  const filterBtns = () => document.querySelectorAll(".ideas-filter-btn");

  function apiBase() {
    const origin = window.location.origin;
    if (origin.includes("127.0.0.1") || origin.includes("localhost")) {
      return "";
    }
    return `http://127.0.0.1:${apiPort()}`;
  }

  function authToken() {
    const cfg = window.AgentRelayConfig;
    if (cfg?.token) return cfg.token;
    return sessionStorage.getItem("agentrelay_token")
      || new URLSearchParams(window.location.search).get("token")
      || "";
  }

  function apiPort() {
    const cfg = window.AgentRelayConfig;
    if (cfg?.port) return cfg.port;
    const fromUrl = new URLSearchParams(window.location.search).get("port");
    const fromStore = sessionStorage.getItem("agentrelay_port");
    return parseInt(fromUrl || fromStore || "9876", 10);
  }

  function setBrainstormStatus(message, tone) {
    const elStatus = document.getElementById("ideas-brainstorm-status");
    if (!elStatus) return;
    elStatus.textContent = message || "";
    elStatus.hidden = !message;
    elStatus.className = "ideas-brainstorm-status hint"
      + (tone ? ` ideas-brainstorm-status--${tone}` : "");
  }

  function authHeader() {
    return { "X-Agent-Token": authToken() };
  }

  async function apiFetch(method, path, body) {
    const opts = {
      method,
      headers: { ...authHeader(), "Content-Type": "application/json" },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const url = path.startsWith("http") ? path : `${apiBase()}${path}`;
    return fetch(url, opts);
  }

  async function loadAgents() {
    try {
      const resp = await apiFetch("GET", "/api/status");
      if (!resp.ok) return;
      const data = await resp.json();
      _agents = data.agents || [];
      _activeAgents = data.active_agents || [];
    } catch (_) { /* offline */ }
  }

  async function loadIdeas() {
    await loadAgents();
    try {
      const resp = await apiFetch("GET", "/api/ideas");
      if (!resp.ok) return;
      const data = await resp.json();
      _ideas = data.ideas || [];
      renderList();
      if (_selectedId) renderForm();
    } catch (_) { /* offline */ }
  }

  function visibleIdeas() {
    if (_filter === "all") return _ideas;
    if (_filter === "done") return _ideas.filter(i => i.status === "done");
    if (_filter === "queued") {
      return _ideas.filter(i => i.status === "queued" || i.status === "in_progress");
    }
    if (_filter === "concept") {
      return _ideas.filter(i => ["exploring", "ready", "concept"].includes(i.status));
    }
    return _ideas.filter(i => i.status === "draft");
  }

  function agentOptions(selected) {
    if (!_agents.length) {
      return '<option value="">No agents configured</option>';
    }
    return _agents.map(a => {
      const id = a.id || a;
      const label = a.label || id;
      const sel = id === selected ? " selected" : "";
      const active = _activeAgents.includes(id) ? " ●" : "";
      return `<option value="${escHtml(id)}"${sel}>${escHtml(label)}${active}</option>`;
    }).join("");
  }

  function renderList() {
    const list = ideasList();
    if (!list) return;
    const items = visibleIdeas();
    if (items.length === 0) {
      list.innerHTML = '<li class="ideas-empty">No ideas yet. Add one!</li>';
      return;
    }
    list.innerHTML = items.map(idea => `
      <li class="ideas-item ${idea.id === _selectedId ? "selected" : ""}" data-id="${idea.id}">
        <div class="ideas-item-top">
          <span class="ideas-item-title">${escHtml(idea.title)}</span>
          <span class="ideas-badge ${PRIORITY_CLASS[idea.priority] || ""}">${PRIORITY_LABEL[idea.priority] || idea.priority}</span>
        </div>
        <div class="ideas-item-meta">
          <span class="ideas-badge ${STATUS_CLASS[idea.status] || ""}">${STATUS_LABEL[idea.status] || idea.status}</span>
          ${idea.findings?.length ? `<span class="ideas-item-date">${idea.findings.length} finding(s)</span>` : ""}
          <span class="ideas-item-date">${fmtDate(idea.updated_at || idea.created_at)}</span>
        </div>
      </li>
    `);

    list.querySelectorAll(".ideas-item").forEach(li => {
      li.addEventListener("click", () => selectIdea(li.dataset.id));
    });
  }

  function selectIdea(id) {
    _selectedId = id;
    _editing = false;
    _capturedImageData = null;
    renderList();
    renderForm();
  }

  function renderFindings(idea) {
    const findings = idea.findings || [];
    if (!findings.length) {
      return '<p class="hint ideas-findings-empty">No findings yet — ask an agent above.</p>';
    }
    return findings.map(f => `
      <article class="ideas-finding" data-finding-id="${f.id}">
        <div class="ideas-finding-head">
          <strong>${escHtml(f.agent || "?")}</strong>
          <span class="hint">${fmtDateTime(f.ts)}</span>
          <button type="button" class="btn ghost small ideas-finding-del" data-id="${f.id}">×</button>
        </div>
        ${f.prompt ? `<p class="ideas-finding-prompt"><em>${escHtml(f.prompt)}</em></p>` : ""}
        ${f.image_data && f.image_data.startsWith("data:image/") ? `<img class="ideas-finding-image" src="${f.image_data}" alt="screenshot">` : ""}
        ${f.content ? `<pre class="ideas-finding-body">${escHtml(f.content)}</pre>` : ""}
      </article>
    `).join("");
  }

  function renderDiscussions(idea) {
    const items = idea.concept_discussions || [];
    if (!items.length) {
      return '<p class="hint">No discussion yet — publish the concept and open discussion with active agents.</p>';
    }
    return items.map(d => `
      <article class="ideas-discussion">
        <div class="ideas-discussion-head">
          <strong>${escHtml(d.agent)}</strong>
          <span class="hint">${fmtDateTime(d.ts)} · ${escHtml(d.source || "agent")}</span>
        </div>
        <pre class="ideas-finding-body">${escHtml(d.content)}</pre>
      </article>
    `).join("");
  }

  function renderForm() {
    const panel = formPanel();
    if (!panel) return;
    const idea = _ideas.find(i => i.id === _selectedId);

    if (!idea) {
      panel.innerHTML = '<p class="ideas-form-hint">Select an idea or add a new one.</p>';
      return;
    }

    if (_editing) {
      panel.innerHTML = `
        <div class="ideas-form">
          <label>Title <input id="ideas-edit-title" type="text" value="${escHtml(idea.title)}"></label>
          <label>Description <textarea id="ideas-edit-desc" rows="3">${escHtml(idea.description || "")}</textarea></label>
          <label>Priority
            <select id="ideas-edit-priority">
              <option value="high" ${idea.priority === "high" ? "selected" : ""}>High</option>
              <option value="medium" ${idea.priority === "medium" ? "selected" : ""}>Medium</option>
              <option value="low" ${idea.priority === "low" ? "selected" : ""}>Low</option>
            </select>
          </label>
          <label>Status
            <select id="ideas-edit-status">
              ${Object.keys(STATUS_LABEL).map(s =>
                `<option value="${s}" ${idea.status === s ? "selected" : ""}>${STATUS_LABEL[s]}</option>`
              ).join("")}
            </select>
          </label>
          <label>Notes <textarea id="ideas-edit-notes" rows="2">${escHtml(idea.notes || "")}</textarea></label>
          <div class="row" style="gap:0.5rem;margin-top:0.5rem">
            <button class="btn primary small" id="ideas-save-btn">Save</button>
            <button class="btn ghost small" id="ideas-cancel-edit-btn">Cancel</button>
          </div>
        </div>
      `;
      el("ideas-save-btn").addEventListener("click", () => saveEdit(idea.id));
      el("ideas-cancel-edit-btn").addEventListener("click", () => { _editing = false; renderForm(); });
      return;
    }

    const agent = idea.brainstorm_agent || idea.assigned_agent || "";
    const published = !!idea.concept_published_at;
    const canQueue = ["draft", "exploring", "ready", "concept"].includes(idea.status);
    const canDone = idea.status === "queued" || idea.status === "in_progress";

    panel.innerHTML = `
      <div class="ideas-detail ideas-workflow">
        <div class="ideas-detail-header">
          <h3 class="ideas-detail-title">${escHtml(idea.title)}</h3>
          <span class="ideas-badge ${PRIORITY_CLASS[idea.priority] || ""}">${PRIORITY_LABEL[idea.priority] || idea.priority}</span>
          <span class="ideas-badge ${STATUS_CLASS[idea.status] || ""}">${STATUS_LABEL[idea.status] || idea.status}</span>
          ${published ? '<span class="ideas-badge status-done">Published</span>' : ""}
        </div>
        ${idea.description ? `<p class="ideas-detail-desc">${escHtml(idea.description)}</p>` : ""}

        <section class="ideas-section ideas-brainstorm-section">
          <h4>Brainstorm with agent</h4>
          <p class="hint">Planning only — each reply is saved under Findings and the Concept below is rebuilt automatically. No implementation until you queue or forward.</p>
          <label>Agent
            <select id="ideas-brainstorm-agent">${agentOptions(agent)}</select>
          </label>
          <label>Your question
            <textarea id="ideas-brainstorm-msg" rows="3" placeholder="What are the risks? What options should we consider?"></textarea>
          </label>
          <div class="row ideas-action-row">
            <button class="btn primary small" id="ideas-brainstorm-btn" ${_busy ? "disabled" : ""}>Ask agent</button>
          </div>
          <p id="ideas-brainstorm-status" class="ideas-brainstorm-status hint" hidden></p>
        </section>

        <section class="ideas-section">
          <h4>Findings <span class="hint">(${(idea.findings || []).length})</span></h4>
          <div id="ideas-findings-list" class="ideas-findings-list">${renderFindings(idea)}</div>
          <label>Add finding manually
            <textarea id="ideas-manual-finding" rows="2" placeholder="Paste notes or conclusions…"></textarea>
          </label>
          <div id="ideas-capture-preview" class="ideas-capture-preview" hidden>
            <img id="ideas-capture-thumb" class="ideas-capture-thumb" src="" alt="screenshot">
            <button type="button" id="ideas-capture-clear" class="btn ghost small ideas-capture-clear">✕</button>
          </div>
          <div class="row ideas-action-row">
            <button class="btn ghost small" id="ideas-save-finding-btn">Save finding</button>
            <button class="btn ghost small" id="ideas-attach-screenshot-btn">Attach image</button>
          </div>
        </section>

        <section class="ideas-section">
          <h4>Concept</h4>
          <p class="hint">Updates automatically when findings change. Edit if needed, then publish for team discussion and forward when ready.</p>
          <textarea id="ideas-concept-editor" class="ideas-concept-editor" rows="8">${escHtml(idea.concept || "")}</textarea>
          <div class="row ideas-action-row">
            <button class="btn ghost small" id="ideas-compile-btn">Build from findings</button>
            <button class="btn ghost small" id="ideas-save-concept-btn">Save concept</button>
            <button class="btn primary small" id="ideas-publish-btn" ${published ? "disabled" : ""}>Publish concept</button>
          </div>
        </section>

        <section class="ideas-section" ${published ? "" : 'style="opacity:0.6"'}>
          <h4>Agent discussion</h4>
          <p class="hint">Share the published concept with every active agent terminal for review.</p>
          <div id="ideas-discussions-list" class="ideas-discussions-list">${renderDiscussions(idea)}</div>
          <div class="row ideas-action-row">
            <button class="btn primary small" id="ideas-discuss-btn" ${published ? "" : "disabled"}>Discuss with active agents</button>
            <button class="btn ghost small" id="ideas-forward-btn" ${published ? "" : "disabled"}>Forward for execution</button>
          </div>
        </section>

        <section class="ideas-section ideas-exec-section">
          <h4>Execution (when agents are idle)</h4>
          <p class="hint">Queue or forward only after brainstorming — auto-run runs when no agent terminals are active.</p>
          <div class="row ideas-action-row">
            ${canQueue ? '<button class="btn ghost small" id="ideas-queue-btn">Queue for auto-run</button>' : ""}
            ${canDone ? '<button class="btn ghost small" id="ideas-done-btn">Mark done</button>' : ""}
            <button class="btn ghost small" id="ideas-edit-btn">Edit</button>
            <button class="btn ghost small ideas-delete-btn" id="ideas-delete-btn">Delete</button>
          </div>
        </section>
      </div>
    `;

    wireFormActions(idea, { canQueue, canDone, published });
  }

  function wireFormActions(idea, { canQueue, canDone, published }) {
    el("ideas-brainstorm-btn")?.addEventListener("click", () => askAgentApi(idea));
    el("ideas-save-finding-btn")?.addEventListener("click", () => saveManualFinding(idea.id));
    el("ideas-attach-screenshot-btn")?.addEventListener("click", attachIdeasScreenshot);
    el("ideas-capture-clear")?.addEventListener("click", clearIdeasCapture);
    el("ideas-compile-btn")?.addEventListener("click", () => compileConcept(idea.id));
    el("ideas-save-concept-btn")?.addEventListener("click", () => saveConcept(idea.id));
    el("ideas-publish-btn")?.addEventListener("click", () => publishConcept(idea.id));
    el("ideas-discuss-btn")?.addEventListener("click", () => discussConcept(idea.id));
    el("ideas-forward-btn")?.addEventListener("click", () => forwardConcept(idea.id));
    if (canQueue) el("ideas-queue-btn")?.addEventListener("click", () => queueIdea(idea.id));
    if (canDone) el("ideas-done-btn")?.addEventListener("click", () => markDone(idea.id));
    el("ideas-edit-btn")?.addEventListener("click", () => { _editing = true; renderForm(); });
    el("ideas-delete-btn")?.addEventListener("click", () => deleteIdea(idea.id));
  }

  async function patchIdea(id, body) {
    const resp = await apiFetch("PATCH", `/api/ideas/${id}`, body);
    if (!resp.ok) return null;
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1) _ideas[idx] = data.idea;
    return data.idea;
  }

  async function askAgentApi(idea) {
    const agent = el("ideas-brainstorm-agent")?.value;
    const message = (el("ideas-brainstorm-msg")?.value || "").trim();
    if (!agent || !message) {
      setBrainstormStatus("Choose an agent and enter a question first.", "warn");
      return;
    }
    const btn = el("ideas-brainstorm-btn");
    if (btn) btn.disabled = true;
    _busy = true;
    setBrainstormStatus(`Asking ${agent}…`, "info");
    try {
      const resp = await apiFetch("POST", `/api/ideas/${idea.id}/brainstorm`, { agent, message });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setBrainstormStatus(data.error || "Analysis request failed", "error");
        return;
      }
      const idx = _ideas.findIndex(i => i.id === idea.id);
      if (idx !== -1 && data.idea) _ideas[idx] = data.idea;
      el("ideas-brainstorm-msg").value = "";
      renderList();
      renderForm();
      setBrainstormStatus("Saved to Findings and Concept updated — planning only, not implementing.", "ok");
    } finally {
      _busy = false;
      if (btn) btn.disabled = false;
    }
  }

  async function saveManualFinding(id) {
    const content = (el("ideas-manual-finding")?.value || "").trim();
    if (!content && !_capturedImageData) return;
    const agent = el("ideas-brainstorm-agent")?.value || "user";
    const body = { content, agent };
    if (_capturedImageData) body.image_data = _capturedImageData;
    const resp = await apiFetch("POST", `/api/ideas/${id}/findings`, body);
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1) _ideas[idx] = data.idea;
    _capturedImageData = null;
    renderList();
    renderForm();
  }

  async function attachIdeasScreenshot() {
    const btn = el("ideas-attach-screenshot-btn");
    if (btn) btn.disabled = true;
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      try {
        const video = document.createElement("video");
        video.srcObject = stream;
        await new Promise((resolve) => { video.onloadedmetadata = resolve; });
        await video.play();
        await new Promise((resolve) => {
          if (typeof video.requestVideoFrameCallback === "function") {
            video.requestVideoFrameCallback(resolve);
          } else {
            requestAnimationFrame(() => requestAnimationFrame(resolve));
          }
        });
        const src = document.createElement("canvas");
        src.width = video.videoWidth;
        src.height = video.videoHeight;
        src.getContext("2d").drawImage(video, 0, 0);
        const MAX_W = 900;
        let dataUrl;
        if (src.width <= MAX_W) {
          dataUrl = src.toDataURL("image/jpeg", 0.82);
        } else {
          const out = document.createElement("canvas");
          const ratio = MAX_W / src.width;
          out.width = MAX_W;
          out.height = Math.round(src.height * ratio);
          out.getContext("2d").drawImage(src, 0, 0, out.width, out.height);
          dataUrl = out.toDataURL("image/jpeg", 0.82);
        }
        _capturedImageData = dataUrl;
        const preview = el("ideas-capture-preview");
        const thumb = el("ideas-capture-thumb");
        if (preview && thumb) {
          thumb.src = dataUrl;
          preview.hidden = false;
        }
      } finally {
        stream.getTracks().forEach((t) => t.stop());
      }
    } catch (e) {
      if (e.name !== "AbortError" && e.name !== "NotAllowedError") {
        setBrainstormStatus("Screen capture failed: " + e.message, "error");
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function clearIdeasCapture() {
    _capturedImageData = null;
    const preview = el("ideas-capture-preview");
    if (preview) preview.hidden = true;
  }

  async function deleteFinding(ideaId, findingId) {
    if (!findingId) {
      setBrainstormStatus("Cannot delete — finding has no id (reload ideas)", "error");
      return;
    }
    if (!confirm("Remove this finding?")) return;
    const resp = await apiFetch("DELETE", `/api/ideas/${ideaId}/findings/${encodeURIComponent(findingId)}`);
    if (!resp.ok) {
      setBrainstormStatus("Could not delete finding — check you are logged in", "error");
      return;
    }
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === ideaId);
    if (idx !== -1) _ideas[idx] = data.idea;
    renderList();
    renderForm();
  }

  async function compileConcept(id) {
    const resp = await apiFetch("POST", `/api/ideas/${id}/compile-concept`);
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1) _ideas[idx] = data.idea;
    renderList();
    renderForm();
  }

  async function saveConcept(id) {
    const concept = el("ideas-concept-editor")?.value || "";
    const body = { concept };
    if (concept.trim()) body.status = "ready";
    await patchIdea(id, body);
    renderList();
    renderForm();
  }

  async function publishConcept(id) {
    const concept = el("ideas-concept-editor")?.value || "";
    if (concept.trim()) await patchIdea(id, { concept });
    const resp = await apiFetch("POST", `/api/ideas/${id}/publish-concept`);
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1) _ideas[idx] = data.idea;
    renderList();
    renderForm();
  }

  async function discussConcept(id) {
    const resp = await apiFetch("POST", `/api/ideas/${id}/discuss`, {});
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      alert(data.error || "Discussion failed — open agent terminals first.");
      return;
    }
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1 && data.idea) _ideas[idx] = data.idea;
    if (typeof window.showView === "function") window.showView("terminals");
    renderForm();
  }

  async function forwardConcept(id) {
    if (!confirm("Forward concept to all active agents and queue for execution?")) return;
    const resp = await apiFetch("POST", `/api/ideas/${id}/forward-concept`, {
      queue_execution: true,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      alert(data.error || "Forward failed.");
      return;
    }
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1 && data.idea) _ideas[idx] = data.idea;
    renderList();
    renderForm();
    if (typeof window.showView === "function") window.showView("terminals");
  }

  function renderAddForm() {
    const panel = formPanel();
    if (!panel) return;
    _selectedId = null;
    _editing = false;
    renderList();
    panel.innerHTML = `
      <div class="ideas-form">
        <h3 style="margin-bottom:0.75rem">New idea</h3>
        <label>Title <input id="ideas-new-title" type="text" placeholder="What's the idea?"></label>
        <label>Description <span class="hint">(optional)</span>
          <textarea id="ideas-new-desc" rows="3" placeholder="More detail…"></textarea>
        </label>
        <label>Priority
          <select id="ideas-new-priority">
            <option value="high">High</option>
            <option value="medium" selected>Medium</option>
            <option value="low">Low</option>
          </select>
        </label>
        <div class="row" style="gap:0.5rem;margin-top:0.5rem">
          <button class="btn primary small" id="ideas-add-submit">Add idea</button>
          <button class="btn ghost small" id="ideas-add-cancel">Cancel</button>
        </div>
      </div>
    `;
    el("ideas-new-title").focus();
    el("ideas-add-submit").addEventListener("click", submitNewIdea);
    el("ideas-add-cancel").addEventListener("click", () => {
      panel.innerHTML = '<p class="ideas-form-hint">Select an idea or add a new one.</p>';
    });
  }

  async function submitNewIdea() {
    const title = (el("ideas-new-title")?.value || "").trim();
    if (!title) return;
    const resp = await apiFetch("POST", "/api/ideas", {
      title,
      description: el("ideas-new-desc")?.value || "",
      priority: el("ideas-new-priority")?.value || "medium",
    });
    if (!resp.ok) return;
    const data = await resp.json();
    _ideas.unshift(data.idea);
    _selectedId = data.idea.id;
    renderList();
    renderForm();
  }

  async function saveEdit(id) {
    const body = {
      title: (el("ideas-edit-title")?.value || "").trim(),
      description: el("ideas-edit-desc")?.value || "",
      priority: el("ideas-edit-priority")?.value || "medium",
      status: el("ideas-edit-status")?.value || "draft",
      notes: el("ideas-edit-notes")?.value || "",
    };
    if (!body.title) return;
    await patchIdea(id, body);
    _editing = false;
    renderList();
    renderForm();
  }

  async function queueIdea(id) {
    await patchIdea(id, { status: "queued" });
    renderList();
    renderForm();
  }

  async function markDone(id) {
    await patchIdea(id, { status: "done" });
    renderList();
    renderForm();
  }

  async function deleteIdea(id) {
    if (!confirm("Delete this idea?")) return;
    const resp = await apiFetch("DELETE", `/api/ideas/${id}`);
    if (!resp.ok) return;
    _ideas = _ideas.filter(i => i.id !== id);
    _selectedId = null;
    renderList();
    formPanel().innerHTML = '<p class="ideas-form-hint">Select an idea or add a new one.</p>';
  }

  function setFilter(f) {
    _filter = f;
    filterBtns().forEach(b => b.classList.toggle("active", b.dataset.filter === f));
    renderList();
  }

  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtDate(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function fmtDateTime(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function init() {
    el("ideas-add-btn")?.addEventListener("click", renderAddForm);
    filterBtns().forEach(btn => {
      btn.addEventListener("click", () => setFilter(btn.dataset.filter));
    });
    document.querySelectorAll(".nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        if (btn.dataset.view === "ideas") loadIdeas();
      });
    });
    formPanel()?.addEventListener("click", (e) => {
      const btn = e.target.closest(".ideas-finding-del");
      if (!btn || !_selectedId) return;
      e.preventDefault();
      e.stopPropagation();
      deleteFinding(_selectedId, btn.dataset.id);
    });
    formPanel().innerHTML = '<p class="ideas-form-hint">Select an idea or add a new one.</p>';
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.ideasLoad = loadIdeas;
})();
