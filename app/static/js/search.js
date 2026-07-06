function escapeHtml(text) {
  return String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function similarityPercent(score) {
  return Math.round((score || 0) * 100);
}

async function loadProjects() {
  const sel = document.getElementById('project');
  try {
    const res = await fetch('/projects');
    const projects = await res.json();
    sel.innerHTML = '<option value="">All projects</option>' +
      projects.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  } catch {
    sel.innerHTML = '<option value="">Failed to load projects</option>';
  }
}

function renderResults(results) {
  if (!results.length) {
    return '<section class="card"><p class="muted">No matching minutes found. Try a different query or upload more minutes.</p></section>';
  }

  return results.map(r => `
    <section class="card search-result-card">
      <div class="search-result-header">
        <div>
          <h2 class="search-result-title">${escapeHtml(r.meeting_title || 'Untitled meeting')}</h2>
          <p class="muted">${escapeHtml(r.project_name || 'Unknown project')} · minutes #${r.minutes_id}</p>
        </div>
        <span class="similarity-badge">${similarityPercent(r.similarity)}% match</span>
      </div>
      ${r.source_url ? `<p class="muted" style="margin-bottom:0.5rem;">Source: ${escapeHtml(r.source_url)}</p>` : ''}
      <p class="search-excerpt">${escapeHtml(r.excerpt || '')}${(r.excerpt || '').length >= 400 ? '…' : ''}</p>
    </section>
  `).join('');
}

async function runSearch() {
  const query = document.getElementById('query').value.trim();
  const projectId = document.getElementById('project').value;
  const limit = document.getElementById('limit').value || '10';
  const resultsEl = document.getElementById('results');
  const btn = document.getElementById('search-btn');

  if (!query) {
    alert('Enter a search query.');
    return;
  }

  btn.disabled = true;
  resultsEl.innerHTML = '<div class="card"><div class="loading-state"><div class="loading-spinner"></div>Searching…</div></div>';

  let url = `/search?q=${encodeURIComponent(query)}&k=${encodeURIComponent(limit)}&detail=true`;
  if (projectId) url += `&project_id=${encodeURIComponent(projectId)}`;

  try {
    const res = await fetch(url);
    if (!res.ok) {
      const txt = await res.text();
      resultsEl.innerHTML = `<div class="card alert alert-error">Error: ${escapeHtml(txt)}</div>`;
      return;
    }
    const data = await res.json();
    resultsEl.innerHTML = renderResults(data);
  } catch (err) {
    resultsEl.innerHTML = `<div class="card alert alert-error">Exception: ${escapeHtml(err?.toString())}</div>`;
  } finally {
    btn.disabled = false;
  }
}

document.getElementById('search-btn').addEventListener('click', runSearch);
document.getElementById('query').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') runSearch();
});

loadProjects();
