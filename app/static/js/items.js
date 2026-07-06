function escapeHtml(text) {
  return String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const TYPE_BADGES = {
  action: 'badge-action',
  decision: 'badge-decision',
  risk: 'badge-risk',
  issue: 'badge-issue',
  accomplishment: 'badge-accomplishment',
  blocker: 'badge-issue',
};

function badgeClass(type) {
  return TYPE_BADGES[type] || 'badge-decision';
}

async function loadProjects() {
  const sel = document.getElementById('filter-project');
  try {
    const res = await fetch('/projects');
    const projects = await res.json();
    sel.innerHTML = '<option value="">All projects</option>' +
      projects.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  } catch {
    sel.innerHTML = '<option value="">Failed to load</option>';
  }
}

function renderItem(item) {
  const done = item.status === 'done';
  return `
    <div class="item-row ${done ? 'item-row-done' : ''}" data-id="${item.id}">
      <div class="item-row-main">
        <div class="item-row-top">
          <span class="badge ${badgeClass(item.type)}">${escapeHtml(item.type)}</span>
          <span class="item-row-title">${escapeHtml(item.title || 'Untitled')}</span>
        </div>
        ${item.detail ? `<p class="item-detail">${escapeHtml(item.detail)}</p>` : ''}
      </div>
      <div class="item-row-fields">
        <div class="field field-compact">
          <label>Owner</label>
          <input type="text" class="edit-owner" value="${escapeHtml(item.owner || '')}" placeholder="Unassigned"/>
        </div>
        <div class="field field-compact">
          <label>Due date</label>
          <input type="date" class="edit-due" value="${escapeHtml(item.due_date || '')}"/>
        </div>
        <div class="field field-compact">
          <label>Status</label>
          <select class="edit-status">
            <option value="open" ${item.status === 'open' ? 'selected' : ''}>Open</option>
            <option value="in_progress" ${item.status === 'in_progress' ? 'selected' : ''}>In progress</option>
            <option value="done" ${item.status === 'done' ? 'selected' : ''}>Done</option>
          </select>
        </div>
        <button type="button" class="btn btn-secondary btn-sm save-item">Save</button>
      </div>
      <div class="item-row-feedback hidden"></div>
    </div>
  `;
}

async function loadItems() {
  const projectId = document.getElementById('filter-project').value;
  const typ = document.getElementById('filter-type').value;
  const status = document.getElementById('filter-status').value;
  const listEl = document.getElementById('items-list');
  const btn = document.getElementById('load-items');

  const params = new URLSearchParams({ limit: '100' });
  if (projectId) params.set('project_id', projectId);
  if (typ) params.set('typ', typ);
  if (status) params.set('status', status);

  btn.disabled = true;
  listEl.innerHTML = '<div class="card"><div class="loading-state"><div class="loading-spinner"></div>Loading items…</div></div>';

  try {
    const res = await fetch(`/items?${params}`);
    if (!res.ok) {
      listEl.innerHTML = `<div class="card alert alert-error">Failed to load items.</div>`;
      return;
    }
    const items = await res.json();
    if (!items.length) {
      listEl.innerHTML = '<div class="card"><p class="muted">No items match your filters.</p></div>';
      return;
    }
    listEl.innerHTML = `<section class="card items-table">${items.map(renderItem).join('')}</section>`;
    bindSaveHandlers();
  } catch (err) {
    listEl.innerHTML = `<div class="card alert alert-error">${escapeHtml(err?.toString())}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function bindSaveHandlers() {
  document.querySelectorAll('.save-item').forEach(btn => {
    btn.addEventListener('click', async () => {
      const row = btn.closest('.item-row');
      const id = row.dataset.id;
      const owner = row.querySelector('.edit-owner').value;
      const dueDate = row.querySelector('.edit-due').value;
      const status = row.querySelector('.edit-status').value;
      const feedback = row.querySelector('.item-row-feedback');

      btn.disabled = true;
      feedback.classList.remove('hidden', 'feedback-error', 'feedback-ok');
      feedback.textContent = 'Saving…';

      try {
        const res = await fetch(`/items/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ owner, due_date: dueDate || '', status }),
        });
        if (!res.ok) {
          const err = await res.text();
          feedback.classList.add('feedback-error');
          feedback.textContent = `Error: ${err}`;
          return;
        }
        const updated = await res.json();
        feedback.classList.add('feedback-ok');
        feedback.textContent = 'Saved';
        row.classList.toggle('item-row-done', updated.status === 'done');
        setTimeout(() => feedback.classList.add('hidden'), 2000);
      } catch (err) {
        feedback.classList.add('feedback-error');
        feedback.textContent = err?.toString() || 'Save failed';
      } finally {
        btn.disabled = false;
      }
    });
  });
}

document.getElementById('load-items').addEventListener('click', loadItems);
loadProjects();
loadItems();
