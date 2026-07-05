function escapeHtml(text) {
  return String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function itemLi(item) {
  const title = escapeHtml(item.title);
  const owner = escapeHtml(item.owner);
  const due = escapeHtml(item.due_date);
  const detail = escapeHtml(item.detail);
  const meta = [owner ? `Owner: ${owner}` : '', due ? `Due: ${due}` : ''].filter(Boolean).join(' · ');
  return `
    <li class="item-card">
      <div class="item-title">${title || 'Untitled'}</div>
      ${meta ? `<div class="item-meta">${meta}</div>` : ''}
      ${detail ? `<p class="item-detail">${detail}</p>` : ''}
    </li>`;
}

function section(title, items, badgeClass) {
  if (!items || !items.length) return '';
  return `
    <div class="result-section">
      <div class="result-header">
        <h2>${title}</h2>
        <span class="badge ${badgeClass}">${items.length}</span>
      </div>
      <ul class="item-list">${items.map(itemLi).join('')}</ul>
    </div>`;
}

async function loadProjects() {
  const sel = document.getElementById('project');
  sel.innerHTML = '<option>Loading…</option>';
  try {
    const res = await fetch('/projects');
    const projects = await res.json();
    if (!projects.length) {
      sel.innerHTML = '<option value="">No projects yet — upload minutes first</option>';
      return;
    }
    sel.innerHTML = projects.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  } catch {
    sel.innerHTML = '<option value="">Failed to load projects</option>';
  }
}

document.getElementById('run').addEventListener('click', async () => {
  const pid = document.getElementById('project').value;
  const days = document.getElementById('days').value || '7';
  const plan = document.getElementById('plan').value;
  const profile = document.getElementById('profile').value || '';
  const out = document.getElementById('out');
  const btn = document.getElementById('run');

  if (!pid) {
    alert('Pick a project first.');
    return;
  }

  btn.disabled = true;
  out.innerHTML = '<div class="card"><div class="loading-state"><div class="loading-spinner"></div>Generating summary…</div></div>';

  const url = `/summary?project_id=${encodeURIComponent(pid)}&days=${encodeURIComponent(days)}&plan=${encodeURIComponent(plan)}&profile=${encodeURIComponent(profile)}`;

  try {
    const res = await fetch(url);
    if (!res.ok) {
      const txt = await res.text();
      out.innerHTML = `<div class="card alert alert-error">Error: ${escapeHtml(txt)}</div>`;
      return;
    }
    const data = await res.json();
    const counts = data.stats?.counts || {};

    const statHtml = `
      <div class="stat-grid">
        <div class="stat-card"><div class="label">Decisions</div><div class="value">${counts.decisions || 0}</div></div>
        <div class="stat-card"><div class="label">Accomplishments</div><div class="value">${counts.accomplishments || 0}</div></div>
        <div class="stat-card"><div class="label">Risks</div><div class="value">${counts.risks || 0}</div></div>
        <div class="stat-card"><div class="label">Issues</div><div class="value">${counts.issues || 0}</div></div>
        <div class="stat-card overdue"><div class="label">Overdue</div><div class="value">${counts.actions_overdue || 0}</div></div>
        <div class="stat-card due-soon"><div class="label">Due Soon</div><div class="value">${counts.actions_due_soon || 0}</div></div>
      </div>`;

    out.innerHTML = `
      <section class="card">
        <p class="muted" style="margin-bottom:1rem;">Window: ${data.window_days} days · Project ID ${data.project_id}</p>
        ${statHtml}
        ${section('Decisions', data.decisions, 'badge-decision')}
        ${section('Accomplishments', data.accomplishments, 'badge-accomplishment')}
        ${section('Risks', data.risks, 'badge-risk')}
        ${section('Issues', data.issues, 'badge-issue')}
        ${section('Actions — Overdue', data.actions?.overdue, 'badge-issue')}
        ${section('Actions — Due Soon', data.actions?.due_soon, 'badge-risk')}
        ${section('Actions — Other Open', data.actions?.open_other, 'badge-action')}
        ${data.plan ? `<div class="result-section"><h2>Plan (Next 7 Days)</h2><pre class="plan-block">${escapeHtml(data.plan)}</pre></div>` : ''}
      </section>`;
  } catch (err) {
    out.innerHTML = `<div class="card alert alert-error">Exception: ${escapeHtml(err?.toString())}</div>`;
  } finally {
    btn.disabled = false;
  }
});

loadProjects();
