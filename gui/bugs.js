/* Bugs panel — list, create, edit, queue, delete */

(function () {
  "use strict";

  const SEVERITY_LABEL = { critical: "Critical", high: "High", medium: "Med", low: "Low" };
  const SEVERITY_CLASS = {
    critical: "severity-critical",
    high: "severity-high",
    medium: "severity-med",
    low: "severity-low",
  };
  const STATUS_LABEL = { draft: "Draft", queued: "Queued", in_progress: "In progress", done: "Done" };
  const STATUS_CLASS = { draft: "status-draft", queued: "status-queued", in_progress: "status-inprogress", done: "status-done" };

  let _bugs = [];
  let _filter = "all";      // "all" | "draft" | "queued" | "done"
  let _selectedId = null;
  let _editing = false;

  // ── DOM refs ──────────────────────────────────────────────────────────────

  function el(id) { return document.getElementById(id); }

  const bugsList     = () => el("bugs-list");
  const formPanel    = () => el("bugs-form-panel");
  const filterBtns   = () => document.querySelectorAll(".bugs-filter-btn");

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

  async function loadBugs() {
    try {
      const resp = await apiFetch("GET", "/api/bugs");
      if (!resp.ok) return;
      const data = await resp.json();
      _bugs = data.bugs || [];
      renderList();
    } catch (_) { /* offline */ }
  }

  function visibleBugs() {
    if (_filter === "all") return _bugs;
    if (_filter === "done") return _bugs.filter(b => b.status === "done");
    if (_filter === "queued") return _bugs.filter(b => b.status === "queued");
    return _bugs.filter(b => b.status === "draft");
  }

  function renderList() {
    const list = bugsList();
    if (!list) return;
    const items = visibleBugs();
    if (items.length === 0) {
      list.innerHTML = '<li class="bugs-empty">No bugs logged yet. Add one!</li>';
      return;
    }
    list.innerHTML = items.map(bug => `
      <li class="bugs-item ${bug.id === _selectedId ? "selected" : ""}" data-id="${bug.id}">
        <div class="bugs-item-top">
          <span class="bugs-item-title">${escHtml(bug.title)}</span>
          <span class="bugs-badge ${SEVERITY_CLASS[bug.severity] || ""}">${SEVERITY_LABEL[bug.severity] || bug.severity}</span>
        </div>
        <div class="bugs-item-meta">
          <span class="bugs-badge ${STATUS_CLASS[bug.status] || ""}">${STATUS_LABEL[bug.status] || bug.status}</span>
          <span class="bugs-item-date">${fmtDate(bug.created_at)}</span>
        </div>
      </li>
    `).join("");

    list.querySelectorAll(".bugs-item").forEach(li => {
      li.addEventListener("click", () => selectBug(li.dataset.id));
    });
  }

  function selectBug(id) {
    _selectedId = id;
    _editing = false;
    renderList();
    renderForm();
  }

  function renderForm() {
    const panel = formPanel();
    if (!panel) return;
    const bug = _bugs.find(b => b.id === _selectedId);

    if (!bug) {
      panel.innerHTML = '<p class="bugs-form-hint">Select a bug or add a new one.</p>';
      return;
    }

    if (_editing) {
      panel.innerHTML = `
        <div class="bugs-form">
          <label>Title
            <input id="bugs-edit-title" type="text" value="${escHtml(bug.title)}">
          </label>
          <label>Description
            <textarea id="bugs-edit-desc" rows="3">${escHtml(bug.description || "")}</textarea>
          </label>
          <label>Steps to reproduce
            <textarea id="bugs-edit-steps" rows="3">${escHtml(bug.steps_to_reproduce || "")}</textarea>
          </label>
          <label>Severity
            <select id="bugs-edit-severity">
              <option value="critical" ${bug.severity === "critical" ? "selected" : ""}>Critical</option>
              <option value="high" ${bug.severity === "high" ? "selected" : ""}>High</option>
              <option value="medium" ${bug.severity === "medium" ? "selected" : ""}>Medium</option>
              <option value="low" ${bug.severity === "low" ? "selected" : ""}>Low</option>
            </select>
          </label>
          <label>Status
            <select id="bugs-edit-status">
              <option value="draft" ${bug.status === "draft" ? "selected" : ""}>Draft</option>
              <option value="queued" ${bug.status === "queued" ? "selected" : ""}>Queued</option>
              <option value="in_progress" ${bug.status === "in_progress" ? "selected" : ""}>In progress</option>
              <option value="done" ${bug.status === "done" ? "selected" : ""}>Done</option>
            </select>
          </label>
          <label>Notes
            <textarea id="bugs-edit-notes" rows="3">${escHtml(bug.notes || "")}</textarea>
          </label>
          <div class="row" style="gap:0.5rem;margin-top:0.5rem">
            <button class="btn primary small" id="bugs-save-btn">Save</button>
            <button class="btn ghost small" id="bugs-cancel-edit-btn">Cancel</button>
          </div>
        </div>
      `;
      el("bugs-save-btn").addEventListener("click", () => saveEdit(bug.id));
      el("bugs-cancel-edit-btn").addEventListener("click", () => { _editing = false; renderForm(); });
      return;
    }

    const canQueue = bug.status === "draft";
    const canDone  = bug.status === "queued" || bug.status === "in_progress";
    panel.innerHTML = `
      <div class="bugs-detail">
        <div class="bugs-detail-header">
          <h3 class="bugs-detail-title">${escHtml(bug.title)}</h3>
          <span class="bugs-badge ${SEVERITY_CLASS[bug.severity] || ""}">${SEVERITY_LABEL[bug.severity] || bug.severity}</span>
          <span class="bugs-badge ${STATUS_CLASS[bug.status] || ""}">${STATUS_LABEL[bug.status] || bug.status}</span>
        </div>
        ${bug.description ? `<p class="bugs-detail-desc">${escHtml(bug.description)}</p>` : ""}
        ${bug.steps_to_reproduce ? `<div class="bugs-detail-steps"><strong>Steps:</strong> ${escHtml(bug.steps_to_reproduce)}</div>` : ""}
        ${bug.notes ? `<div class="bugs-detail-notes"><strong>Notes:</strong> ${escHtml(bug.notes)}</div>` : ""}
        <p class="hint" style="margin-top:0.5rem">Logged ${fmtDate(bug.created_at)}</p>
        <div class="row" style="gap:0.5rem;margin-top:1rem;flex-wrap:wrap">
          ${canQueue ? '<button class="btn primary small" id="bugs-queue-btn">Queue for auto-run</button>' : ""}
          ${canDone  ? '<button class="btn ghost small" id="bugs-done-btn">Mark fixed</button>' : ""}
          <button class="btn ghost small" id="bugs-edit-btn">Edit</button>
          <button class="btn ghost small bugs-delete-btn" id="bugs-delete-btn">Delete</button>
        </div>
      </div>
    `;
    if (canQueue) el("bugs-queue-btn").addEventListener("click", () => queueBug(bug.id));
    if (canDone)  el("bugs-done-btn").addEventListener("click",  () => markDone(bug.id));
    el("bugs-edit-btn").addEventListener("click", () => { _editing = true; renderForm(); });
    el("bugs-delete-btn").addEventListener("click", () => deleteBug(bug.id));
  }

  // ── Add form ──────────────────────────────────────────────────────────────

  function renderAddForm() {
    const panel = formPanel();
    if (!panel) return;
    _selectedId = null;
    _editing = false;
    renderList();
    panel.innerHTML = `
      <div class="bugs-form">
        <h3 style="margin-bottom:0.75rem">New bug</h3>
        <label>Title
          <input id="bugs-new-title" type="text" placeholder="What broke?">
        </label>
        <label>Description <span class="hint" style="font-size:0.8rem">(optional)</span>
          <textarea id="bugs-new-desc" rows="3" placeholder="What happened?"></textarea>
        </label>
        <label>Steps to reproduce <span class="hint" style="font-size:0.8rem">(optional)</span>
          <textarea id="bugs-new-steps" rows="2" placeholder="1. Open…\n2. Click…"></textarea>
        </label>
        <label>Severity
          <select id="bugs-new-severity">
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium" selected>Medium</option>
            <option value="low">Low</option>
          </select>
        </label>
        <div class="row" style="gap:0.5rem;margin-top:0.5rem">
          <button class="btn primary small" id="bugs-add-submit">Add bug</button>
          <button class="btn ghost small" id="bugs-add-cancel">Cancel</button>
        </div>
      </div>
    `;
    el("bugs-new-title").focus();
    el("bugs-add-submit").addEventListener("click", submitNewBug);
    el("bugs-add-cancel").addEventListener("click", () => {
      panel.innerHTML = '<p class="bugs-form-hint">Select a bug or add a new one.</p>';
    });
    el("bugs-new-title").addEventListener("keydown", e => {
      if (e.key === "Enter") submitNewBug();
    });
  }

  // ── CRUD actions ──────────────────────────────────────────────────────────

  async function submitNewBug() {
    const title = (el("bugs-new-title")?.value || "").trim();
    if (!title) { el("bugs-new-title")?.focus(); return; }
    const body = {
      title,
      description: el("bugs-new-desc")?.value || "",
      steps_to_reproduce: el("bugs-new-steps")?.value || "",
      severity: el("bugs-new-severity")?.value || "medium",
    };
    const resp = await apiFetch("POST", "/api/bugs", body);
    if (!resp.ok) return;
    const data = await resp.json();
    _bugs.unshift(data.bug);
    _bugs.sort((a, b) => {
      const SR = { critical: 0, high: 1, medium: 2, low: 3 };
      return (SR[a.severity] ?? 2) - (SR[b.severity] ?? 2) || a.created_at - b.created_at;
    });
    _selectedId = data.bug.id;
    _editing = false;
    renderList();
    renderForm();
  }

  async function saveEdit(id) {
    const body = {
      title: (el("bugs-edit-title")?.value || "").trim(),
      description: el("bugs-edit-desc")?.value || "",
      steps_to_reproduce: el("bugs-edit-steps")?.value || "",
      severity: el("bugs-edit-severity")?.value || "medium",
      status: el("bugs-edit-status")?.value || "draft",
      notes: el("bugs-edit-notes")?.value || "",
    };
    if (!body.title) { el("bugs-edit-title")?.focus(); return; }
    const resp = await apiFetch("PATCH", `/api/bugs/${id}`, body);
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _bugs.findIndex(b => b.id === id);
    if (idx !== -1) _bugs[idx] = data.bug;
    _editing = false;
    renderList();
    renderForm();
  }

  async function queueBug(id) {
    const resp = await apiFetch("PATCH", `/api/bugs/${id}`, { status: "queued" });
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _bugs.findIndex(b => b.id === id);
    if (idx !== -1) _bugs[idx] = data.bug;
    renderList();
    renderForm();
  }

  async function markDone(id) {
    const resp = await apiFetch("PATCH", `/api/bugs/${id}`, { status: "done" });
    if (!resp.ok) return;
    const data = await resp.json();
    const idx = _bugs.findIndex(b => b.id === id);
    if (idx !== -1) _bugs[idx] = data.bug;
    renderList();
    renderForm();
  }

  async function deleteBug(id) {
    if (!confirm("Delete this bug?")) return;
    const resp = await apiFetch("DELETE", `/api/bugs/${id}`);
    if (!resp.ok) return;
    _bugs = _bugs.filter(b => b.id !== id);
    _selectedId = null;
    renderList();
    const panel = formPanel();
    if (panel) panel.innerHTML = '<p class="bugs-form-hint">Select a bug or add a new one.</p>';
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
    // Add bug button
    const addBtn = el("bugs-add-btn");
    if (addBtn) addBtn.addEventListener("click", renderAddForm);

    // Filter buttons
    filterBtns().forEach(btn => {
      btn.addEventListener("click", () => setFilter(btn.dataset.filter));
    });

    // Load when view is shown
    document.querySelectorAll(".nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        if (btn.dataset.view === "bugs") loadBugs();
      });
    });

    // Reset form panel placeholder
    const panel = formPanel();
    if (panel) panel.innerHTML = '<p class="bugs-form-hint">Select a bug or add a new one.</p>';
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expose for external refresh (e.g., when view activates)
  window.bugsLoad = loadBugs;
})();
