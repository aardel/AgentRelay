/* Ideas panel — list, create, edit, queue, delete */

(function () {
  "use strict";

  const PRIORITY_LABEL = { high: "High", medium: "Med", low: "Low" };
  const PRIORITY_CLASS = { high: "priority-high", medium: "priority-med", low: "priority-low" };
  const STATUS_LABEL = { draft: "Draft", queued: "Queued", in_progress: "In progress", done: "Done" };
  const STATUS_CLASS = { draft: "status-draft", queued: "status-queued", in_progress: "status-inprogress", done: "status-done" };

  let _ideas = [];
  let _filter = "all";      // "all" | "draft" | "queued" | "done"
  let _selectedId = null;
  let _editing = false;

  // ── DOM refs ──────────────────────────────────────────────────────────────

  function el(id) { return document.getElementById(id); }

  const ideasList    = () => el("ideas-list");
  const formPanel    = () => el("ideas-form-panel");
  const filterBtns   = () => document.querySelectorAll(".ideas-filter-btn");

  // ── API helpers ───────────────────────────────────────────────────────────

  function authHeader() {
    return { "X-Agent-Token": window.AGENT_TOKEN || "" };
  }

  async function apiFetch(method, path, body) {
    const opts = {
      method,
      headers: { ...authHeader(), "Content-Type": "application/json" },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const resp = await fetch(path, opts);
    return resp;
  }

  // ── Load & render ─────────────────────────────────────────────────────────

  async function loadIdeas() {
    try {
      const resp = await apiFetch("GET", "/api/ideas");
      if (!resp.ok) return;
      const data = await resp.json();
      _ideas = data.ideas || [];
      renderList();
    } catch (_) { /* offline */ }
  }

  function visibleIdeas() {
    if (_filter === "all") return _ideas;
    if (_filter === "done") return _ideas.filter(i => i.status === "done");
    if (_filter === "queued") return _ideas.filter(i => i.status === "queued");
    return _ideas.filter(i => i.status === "draft");
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
          <span class="ideas-item-date">${fmtDate(idea.created_at)}</span>
        </div>
      </li>
    `).join("");

    list.querySelectorAll(".ideas-item").forEach(li => {
      li.addEventListener("click", () => selectIdea(li.dataset.id));
    });
  }

  function selectIdea(id) {
    _selectedId = id;
    _editing = false;
    renderList();
    renderForm();
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
          <label>Title
            <input id="ideas-edit-title" type="text" value="${escHtml(idea.title)}">
          </label>
          <label>Description
            <textarea id="ideas-edit-desc" rows="4">${escHtml(idea.description || "")}</textarea>
          </label>
          <label>Priority
            <select id="ideas-edit-priority">
              <option value="high" ${idea.priority === "high" ? "selected" : ""}>High</option>
              <option value="medium" ${idea.priority === "medium" ? "selected" : ""}>Medium</option>
              <option value="low" ${idea.priority === "low" ? "selected" : ""}>Low</option>
            </select>
          </label>
          <label>Status
            <select id="ideas-edit-status">
              <option value="draft" ${idea.status === "draft" ? "selected" : ""}>Draft</option>
              <option value="queued" ${idea.status === "queued" ? "selected" : ""}>Queued</option>
              <option value="in_progress" ${idea.status === "in_progress" ? "selected" : ""}>In progress</option>
              <option value="done" ${idea.status === "done" ? "selected" : ""}>Done</option>
            </select>
          </label>
          <label>Notes
            <textarea id="ideas-edit-notes" rows="3">${escHtml(idea.notes || "")}</textarea>
          </label>
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

    const canQueue = idea.status === "draft";
    const canDone  = idea.status === "queued" || idea.status === "in_progress";
    panel.innerHTML = `
      <div class="ideas-detail">
        <div class="ideas-detail-header">
          <h3 class="ideas-detail-title">${escHtml(idea.title)}</h3>
          <span class="ideas-badge ${PRIORITY_CLASS[idea.priority] || ""}">${PRIORITY_LABEL[idea.priority] || idea.priority}</span>
          <span class="ideas-badge ${STATUS_CLASS[idea.status] || ""}">${STATUS_LABEL[idea.status] || idea.status}</span>
        </div>
        ${idea.description ? `<p class="ideas-detail-desc">${escHtml(idea.description)}</p>` : ""}
        ${idea.notes ? `<div class="ideas-detail-notes"><strong>Notes:</strong> ${escHtml(idea.notes)}</div>` : ""}
        <p class="hint" style="margin-top:0.5rem">Added ${fmtDate(idea.created_at)}</p>
        <div class="row" style="gap:0.5rem;margin-top:1rem;flex-wrap:wrap">
          ${canQueue ? '<button class="btn primary small" id="ideas-queue-btn">Queue for auto-run</button>' : ""}
          ${canDone  ? '<button class="btn ghost small" id="ideas-done-btn">Mark done</button>' : ""}
          <button class="btn ghost small" id="ideas-edit-btn">Edit</button>
          <button class="btn ghost small ideas-delete-btn" id="ideas-delete-btn">Delete</button>
        </div>
      </div>
    `;
    if (canQueue) el("ideas-queue-btn").addEventListener("click", () => queueIdea(idea.id));
    if (canDone)  el("ideas-done-btn").addEventListener("click",  () => markDone(idea.id));
    el("ideas-edit-btn").addEventListener("click", () => { _editing = true; renderForm(); });
    el("ideas-delete-btn").addEventListener("click", () => deleteIdea(idea.id));
  }

  // ── Add form ──────────────────────────────────────────────────────────────

  function renderAddForm() {
    const panel = formPanel();
    if (!panel) return;
    _selectedId = null;
    _editing = false;
    renderList();
    panel.innerHTML = `
      <div class="ideas-form">
        <h3 style="margin-bottom:0.75rem">New idea</h3>
        <label>Title
          <input id="ideas-new-title" type="text" placeholder="What's the idea?">
        </label>
        <label>Description <span class="hint" style="font-size:0.8rem">(optional)</span>
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
    el("ideas-new-title").addEventListener("keydown", e => {
      if (e.key === "Enter") submitNewIdea();
    });
  }

  // ── CRUD actions ──────────────────────────────────────────────────────────

  async function submitNewIdea() {
    const title = (el("ideas-new-title")?.value || "").trim();
    if (!title) { el("ideas-new-title")?.focus(); return; }
    const body = {
      title,
      description: el("ideas-new-desc")?.value || "",
      priority: el("ideas-new-priority")?.value || "medium",
    };
    const resp = await apiFetch("POST", "/api/ideas", body);
    if (!resp.ok) return;
    const data = await resp.json();
    _ideas.unshift(data.idea);
    _ideas.sort((a, b) => {
      const PR = { high: 0, medium: 1, low: 2 };
      return (PR[a.priority] ?? 1) - (PR[b.priority] ?? 1) || a.created_at - b.created_at;
    });
    _selectedId = data.idea.id;
    _editing = false;
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
    if (!body.title) { el("ideas-edit-title")?.focus(); return; }
    const resp = await apiFetch("PATCH", `/api/ideas/${id}`, body);
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1) _ideas[idx] = data.idea;
    _editing = false;
    renderList();
    renderForm();
  }

  async function queueIdea(id) {
    const resp = await apiFetch("PATCH", `/api/ideas/${id}`, { status: "queued" });
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1) _ideas[idx] = data.idea;
    renderList();
    renderForm();
  }

  async function markDone(id) {
    const resp = await apiFetch("PATCH", `/api/ideas/${id}`, { status: "done" });
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _ideas.findIndex(i => i.id === id);
    if (idx !== -1) _ideas[idx] = data.idea;
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
    const panel = formPanel();
    if (panel) panel.innerHTML = '<p class="ideas-form-hint">Select an idea or add a new one.</p>';
  }

  // ── Filters ───────────────────────────────────────────────────────────────

  function setFilter(f) {
    _filter = f;
    filterBtns().forEach(b => b.classList.toggle("active", b.dataset.filter === f));
    renderList();
  }

  // ── Utility ───────────────────────────────────────────────────────────────

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

  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    // Add idea button
    const addBtn = el("ideas-add-btn");
    if (addBtn) addBtn.addEventListener("click", renderAddForm);

    // Filter buttons
    filterBtns().forEach(btn => {
      btn.addEventListener("click", () => setFilter(btn.dataset.filter));
    });

    // Load when view is shown
    document.querySelectorAll(".nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        if (btn.dataset.view === "ideas") loadIdeas();
      });
    });

    // Reset form panel placeholder
    const panel = formPanel();
    if (panel) panel.innerHTML = '<p class="ideas-form-hint">Select an idea or add a new one.</p>';
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expose for external refresh (e.g., when view activates)
  window.ideasLoad = loadIdeas;
})();
