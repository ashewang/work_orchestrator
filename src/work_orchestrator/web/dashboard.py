"""Dashboard HTML with inline CSS and vanilla JS."""


def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Work Orchestrator</title>
<style>
  :root {
    --bg: #0a0c10; --bg-raised: #0d1117; --surface: #151b23;
    --surface-hover: #1c2333; --border: #262d38; --border-subtle: #1e252f;
    --text: #e2e8f0; --text-secondary: #94a3b8; --text-dim: #64748b;
    --todo: #94a3b8; --in-progress: #60a5fa; --done: #4ade80;
    --blocked: #f87171; --review: #c084fc;
    --accent: #60a5fa; --link: #60a5fa;
    --p0: #ef4444; --p1: #f97316; --p2: #eab308; --p3: #60a5fa;
    --p4: #94a3b8; --p5: #64748b; --p6: #475569;
    --radius: 10px; --radius-sm: 6px;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  .page { max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }

  /* ── Header ──────────────────────────── */
  .page-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 32px; padding-bottom: 20px; border-bottom: 1px solid var(--border-subtle);
  }
  .page-header h1 {
    font-size: 22px; font-weight: 700; letter-spacing: -0.3px;
    background: linear-gradient(135deg, #e2e8f0, #94a3b8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .header-meta { font-size: 12px; color: var(--text-dim); display: flex; align-items: center; gap: 12px; }
  .header-meta button {
    background: var(--surface); color: var(--text-secondary); border: 1px solid var(--border);
    padding: 5px 14px; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px;
    transition: all 0.15s;
  }
  .header-meta button:hover { color: var(--text); border-color: var(--text-dim); background: var(--surface-hover); }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--done); display: inline-block; }
  .status-dot.loading { background: var(--in-progress); animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  /* ── Project Card ────────────────────── */
  .project-card {
    background: var(--bg-raised); border: 1px solid var(--border-subtle);
    border-radius: var(--radius); margin-bottom: 24px; overflow: hidden;
    transition: border-color 0.2s;
  }
  .project-card:hover { border-color: var(--border); }
  .project-head {
    padding: 18px 22px; cursor: pointer; user-select: none;
    display: flex; justify-content: space-between; align-items: center;
  }
  .project-head:hover { background: var(--surface); }
  .project-name { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
  .project-name .chevron {
    display: inline-block; font-size: 11px; color: var(--text-dim); transition: transform 0.2s;
  }
  .project-card.expanded .project-name .chevron { transform: rotate(90deg); }
  .project-badges { display: flex; gap: 8px; align-items: center; }
  .count-badge {
    display: inline-flex; align-items: center; gap: 4px; padding: 2px 9px;
    border-radius: 12px; font-size: 11px; font-weight: 600;
  }
  .count-badge .dot { width: 6px; height: 6px; border-radius: 50%; }
  .count-badge.todo { background: rgba(148,163,184,0.1); color: var(--todo); }
  .count-badge.todo .dot { background: var(--todo); }
  .count-badge.in-progress { background: rgba(96,165,250,0.1); color: var(--in-progress); }
  .count-badge.in-progress .dot { background: var(--in-progress); }
  .count-badge.done { background: rgba(74,222,128,0.1); color: var(--done); }
  .count-badge.done .dot { background: var(--done); }
  .count-badge.blocked { background: rgba(248,113,113,0.1); color: var(--blocked); }
  .count-badge.blocked .dot { background: var(--blocked); }
  .count-badge.review { background: rgba(192,132,252,0.1); color: var(--review); }
  .count-badge.review .dot { background: var(--review); }

  .project-body { display: none; border-top: 1px solid var(--border-subtle); }
  .project-card.expanded .project-body { display: block; }

  .project-meta-bar {
    padding: 12px 22px; font-size: 12px; color: var(--text-dim);
    display: flex; gap: 16px; align-items: center; border-bottom: 1px solid var(--border-subtle);
    background: var(--surface);
  }
  .project-meta-bar code {
    background: var(--bg); padding: 1px 6px; border-radius: 4px;
    font-size: 11px; color: var(--text-secondary);
  }

  .progress-row {
    padding: 14px 22px; display: flex; align-items: center; gap: 14px;
    border-bottom: 1px solid var(--border-subtle);
  }
  .progress-track {
    flex: 1; height: 6px; background: var(--surface);
    border-radius: 3px; overflow: hidden;
  }
  .progress-fill { height: 100%; background: var(--done); border-radius: 3px; transition: width 0.4s ease; }
  .progress-label { font-size: 12px; color: var(--text-dim); min-width: 36px; text-align: right; font-weight: 600; }

  /* ── Task Rows ───────────────────────── */
  .task-list { padding: 6px 0; }
  .task-row {
    padding: 10px 22px; display: flex; align-items: center; gap: 12px;
    transition: background 0.1s;
  }
  .task-row:hover { background: var(--surface); }
  .task-row.subtask { padding-left: 52px; }

  .status-icon { width: 18px; height: 18px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
  .status-icon svg { width: 16px; height: 16px; }
  .status-icon.todo svg { color: var(--todo); }
  .status-icon.in-progress svg { color: var(--in-progress); }
  .status-icon.done svg { color: var(--done); }
  .status-icon.blocked svg { color: var(--blocked); }
  .status-icon.review svg { color: var(--review); }

  .prio-tag {
    font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;
    flex-shrink: 0; letter-spacing: 0.3px;
  }
  .prio-tag.p0 { background: rgba(239,68,68,0.15); color: var(--p0); }
  .prio-tag.p1 { background: rgba(249,115,22,0.15); color: var(--p1); }
  .prio-tag.p2 { background: rgba(234,179,8,0.15); color: var(--p2); }
  .prio-tag.p3 { background: rgba(96,165,250,0.1); color: var(--p3); }
  .prio-tag.p4 { background: rgba(148,163,184,0.08); color: var(--p4); }
  .prio-tag.p5 { background: rgba(100,116,139,0.08); color: var(--p5); }
  .prio-tag.p6 { background: rgba(71,85,105,0.08); color: var(--p6); }

  .task-info { flex: 1; min-width: 0; }
  .task-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .task-sub-line { font-size: 11px; color: var(--text-dim); display: flex; gap: 10px; flex-wrap: wrap; margin-top: 1px; }
  .task-sub-line code { font-size: 10px; background: var(--bg); padding: 0 4px; border-radius: 3px; }
  .task-sub-line a { color: var(--link); text-decoration: none; }
  .task-sub-line a:hover { text-decoration: underline; }
  .task-slug { font-size: 11px; color: var(--text-dim); font-family: monospace; flex-shrink: 0; }

  /* ── Empty State ─────────────────────── */
  .empty {
    text-align: center; padding: 64px 24px; color: var(--text-dim);
  }
  .empty h3 { font-size: 16px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
  .empty p { font-size: 13px; }
  .empty code { background: var(--surface); padding: 2px 8px; border-radius: 4px; font-size: 12px; }

  /* ── Filter Tabs ─────────────────────── */
  .filter-bar {
    padding: 8px 22px; display: flex; gap: 4px; align-items: center;
    border-bottom: 1px solid var(--border-subtle);
  }
  .filter-tab {
    background: none; border: none; color: var(--text-dim); font-size: 11px;
    font-weight: 500; padding: 4px 10px; border-radius: 4px; cursor: pointer;
    transition: all 0.1s;
  }
  .filter-tab:hover { color: var(--text-secondary); background: var(--surface); }
  .filter-tab.active { color: var(--text); background: var(--surface-hover); }
</style>
</head>
<body>
<div class="page">
  <div class="page-header">
    <h1>Work Orchestrator</h1>
    <div class="header-meta">
      <span><span class="status-dot loading" id="status-dot"></span> Loading</span>
      <button onclick="refreshAll()">Refresh</button>
    </div>
  </div>
  <div id="projects"></div>
</div>

<script>
const API = '';
const projectFilters = {};

const STATUS_ICONS = {
  'todo': '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/></svg>',
  'in-progress': '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l2.5 1.5" stroke-linecap="round"/></svg>',
  'done': '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M5.5 8l1.5 2 3.5-4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  'blocked': '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M6 6l4 4M10 6l-4 4" stroke-linecap="round"/></svg>',
  'review': '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/></svg>',
};

async function fetchJSON(path) {
  const res = await fetch(API + path);
  if (!res.ok) return null;
  return res.json();
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function toggleProject(id) {
  const card = document.getElementById('proj-' + id);
  card.classList.toggle('expanded');
}

function setFilter(projectId, status) {
  projectFilters[projectId] = status;
  loadProjectTasks(projectId);
  // Update active tab
  document.querySelectorAll(`#proj-${projectId} .filter-tab`).forEach(t => {
    t.classList.toggle('active', t.dataset.status === (status || 'all'));
  });
}

async function loadProjectTasks(projectId) {
  const statusFilter = projectFilters[projectId] || null;
  const url = statusFilter
    ? `/api/projects/${projectId}/tasks?status=${statusFilter}`
    : `/api/projects/${projectId}/tasks`;
  const tasks = await fetchJSON(url) || [];
  const listEl = document.getElementById('tasks-' + projectId);
  if (!tasks.length) {
    listEl.innerHTML = '<div class="empty" style="padding:32px"><p>No tasks match this filter</p></div>';
    return;
  }
  let html = '';
  for (const task of tasks) {
    html += renderTask(task, false);
    if (task.subtasks) {
      for (const sub of task.subtasks) {
        html += renderTask(sub, true);
      }
    }
  }
  listEl.innerHTML = html;
}

function renderTask(task, isSubtask) {
  const cls = isSubtask ? 'task-row subtask' : 'task-row';
  const statusCls = task.status.replace(' ', '-');
  const icon = STATUS_ICONS[statusCls] || STATUS_ICONS['todo'];
  const prio = task.priority != null ? task.priority : 3;

  let subLine = [];
  if (task.description) subLine.push(esc(task.description));
  if (task.branch_name) subLine.push('branch: <code>' + esc(task.branch_name) + '</code>');
  if (task.worktree_path) subLine.push('worktree: <code>' + esc(task.worktree_path) + '</code>');
  if (task.pr_url) subLine.push('<a href="' + esc(task.pr_url) + '" target="_blank" rel="noopener">PR</a>');
  if (task.depends_on && task.depends_on.length) subLine.push('deps: ' + task.depends_on.map(d => '<code>' + esc(d) + '</code>').join(', '));

  return `<div class="${cls}">
    <span class="status-icon ${statusCls}">${icon}</span>
    <span class="prio-tag p${prio}">P${prio}</span>
    <div class="task-info">
      <div class="task-name">${esc(task.title)}</div>
      ${subLine.length ? '<div class="task-sub-line">' + subLine.join(' &middot; ') + '</div>' : ''}
    </div>
    <span class="task-slug">${esc(task.id)}</span>
  </div>`;
}

function renderProjectCard(project, summary, tasks) {
  const c = summary ? summary.counts : {};
  const pct = summary ? summary.progress_pct : 0;

  function badge(status, label, count) {
    if (!count) return '';
    return `<span class="count-badge ${status}"><span class="dot"></span>${count} ${label}</span>`;
  }

  const statuses = ['all', 'todo', 'in-progress', 'done', 'blocked', 'review'];
  const filterTabs = statuses.map(s => {
    const label = s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1).replace('-', ' ');
    const active = s === 'all' ? ' active' : '';
    return `<button class="filter-tab${active}" data-status="${s}" onclick="setFilter('${project.id}', ${s === 'all' ? 'null' : "'" + s + "'"})">
      ${label}</button>`;
  }).join('');

  let taskHtml = '';
  if (!tasks || !tasks.length) {
    taskHtml = '<div class="empty" style="padding:32px"><p>No tasks yet. Create one with <code>wo task add</code></p></div>';
  } else {
    for (const task of tasks) {
      taskHtml += renderTask(task, false);
      if (task.subtasks) {
        for (const sub of task.subtasks) {
          taskHtml += renderTask(sub, true);
        }
      }
    }
  }

  return `<div class="project-card expanded" id="proj-${project.id}">
    <div class="project-head" onclick="toggleProject('${project.id}')">
      <span class="project-name">
        <span class="chevron">&#9654;</span>
        ${esc(project.name)}
      </span>
      <div class="project-badges">
        ${badge('in-progress', 'active', c['in-progress'])}
        ${badge('todo', 'todo', c.todo)}
        ${badge('review', 'review', c.review)}
        ${badge('blocked', 'blocked', c.blocked)}
        ${badge('done', 'done', c.done)}
      </div>
    </div>
    <div class="project-body">
      <div class="project-meta-bar">
        <span>Repo: <code>${esc(project.repo_path)}</code></span>
        <span>Branch: <code>${esc(project.default_branch)}</code></span>
        ${project.slack_channel ? '<span>Slack: <code>' + esc(project.slack_channel) + '</code></span>' : ''}
      </div>
      <div class="progress-row">
        <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
        <span class="progress-label">${pct}%</span>
      </div>
      <div class="filter-bar">${filterTabs}</div>
      <div class="task-list" id="tasks-${project.id}">${taskHtml}</div>
    </div>
  </div>`;
}

async function loadAll() {
  const dot = document.getElementById('status-dot');
  dot.classList.add('loading');

  const projects = await fetchJSON('/api/projects') || [];
  const container = document.getElementById('projects');

  if (!projects.length) {
    container.innerHTML = '<div class="empty"><h3>No projects</h3><p>Create one with the CLI or MCP tools.</p></div>';
    dot.classList.remove('loading');
    return;
  }

  const results = await Promise.all(projects.map(async p => {
    const [summary, tasks] = await Promise.all([
      fetchJSON(`/api/projects/${p.id}/summary`),
      fetchJSON(`/api/projects/${p.id}/tasks`),
    ]);
    return { project: p, summary, tasks };
  }));

  container.innerHTML = results.map(r => renderProjectCard(r.project, r.summary, r.tasks)).join('');

  dot.classList.remove('loading');
  dot.parentElement.childNodes[1].textContent = ' ' + new Date().toLocaleTimeString();
}

function refreshAll() { loadAll(); }

loadAll();
setInterval(loadAll, 30000);
</script>
</body>
</html>"""
