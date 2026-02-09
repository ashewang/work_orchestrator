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
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --text-muted: #8b949e; --text-dim: #6e7681;
    --todo: #8b949e; --in-progress: #58a6ff; --done: #3fb950; --blocked: #f85149;
    --accent: #58a6ff; --link: #58a6ff;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }
  .container { max-width: 960px; margin: 0 auto; padding: 24px 16px; }

  /* Header */
  header { display: flex; justify-content: space-between; align-items: center;
           padding-bottom: 16px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
  header h1 { font-size: 20px; font-weight: 600; }
  header select { background: var(--surface); color: var(--text); border: 1px solid var(--border);
                  padding: 6px 12px; border-radius: 6px; font-size: 14px; cursor: pointer; }

  /* Project info */
  .project-info { background: var(--surface); border: 1px solid var(--border);
                  border-radius: 8px; padding: 16px; margin-bottom: 20px; }
  .project-info h2 { font-size: 16px; margin-bottom: 8px; }
  .project-meta { font-size: 13px; color: var(--text-muted); }
  .project-meta code { background: var(--bg); padding: 2px 6px; border-radius: 4px; font-size: 12px; }

  /* Summary bar */
  .summary { display: flex; gap: 16px; align-items: center; margin-bottom: 24px; flex-wrap: wrap; }
  .stat { display: flex; align-items: center; gap: 6px; font-size: 14px; }
  .stat .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .stat .dot.todo { background: var(--todo); }
  .stat .dot.in-progress { background: var(--in-progress); }
  .stat .dot.done { background: var(--done); }
  .stat .dot.blocked { background: var(--blocked); }
  .progress-bar { flex: 1; min-width: 120px; height: 8px; background: var(--surface);
                  border-radius: 4px; overflow: hidden; border: 1px solid var(--border); }
  .progress-bar .fill { height: 100%; background: var(--done); transition: width 0.3s; }
  .progress-pct { font-size: 13px; color: var(--text-muted); min-width: 40px; }

  /* Task list */
  .task-list { display: flex; flex-direction: column; gap: 2px; }
  .task-card { background: var(--surface); border: 1px solid var(--border);
               border-radius: 8px; padding: 12px 16px; }
  .task-card.subtask { margin-left: 32px; border-left: 3px solid var(--border); }
  .task-header { display: flex; align-items: center; gap: 10px; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px;
           font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .badge.todo { background: rgba(139,148,158,0.15); color: var(--todo); }
  .badge.in-progress { background: rgba(88,166,255,0.15); color: var(--in-progress); }
  .badge.done { background: rgba(63,185,80,0.15); color: var(--done); }
  .badge.blocked { background: rgba(248,81,73,0.15); color: var(--blocked); }
  .task-title { font-weight: 600; font-size: 14px; }
  .task-id { font-size: 12px; color: var(--text-dim); font-family: monospace; }
  .task-details { margin-top: 6px; font-size: 13px; color: var(--text-muted); display: flex;
                  flex-direction: column; gap: 3px; }
  .task-details code { background: var(--bg); padding: 1px 5px; border-radius: 3px; font-size: 12px; }
  .task-details a { color: var(--link); text-decoration: none; }
  .task-details a:hover { text-decoration: underline; }
  .dep-list { font-size: 12px; color: var(--text-dim); }

  /* Empty state */
  .empty { text-align: center; padding: 48px; color: var(--text-muted); }
  .empty h3 { margin-bottom: 8px; }

  /* Refresh indicator */
  .refresh-bar { display: flex; justify-content: space-between; align-items: center;
                 margin-bottom: 16px; font-size: 12px; color: var(--text-dim); }
  .refresh-bar button { background: var(--surface); color: var(--text-muted); border: 1px solid var(--border);
                        padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  .refresh-bar button:hover { color: var(--text); border-color: var(--text-muted); }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Work Orchestrator</h1>
    <select id="project-picker"><option value="">Loading...</option></select>
  </header>
  <div id="content">
    <div class="empty"><h3>Select a project</h3><p>Choose a project from the dropdown above.</p></div>
  </div>
</div>

<script>
const API = '';
let currentProject = null;
let refreshTimer = null;

async function fetchJSON(path) {
  const res = await fetch(API + path);
  if (!res.ok) return null;
  return res.json();
}

async function loadProjects() {
  const picker = document.getElementById('project-picker');
  const projects = await fetchJSON('/api/projects');
  if (!projects || projects.length === 0) {
    picker.innerHTML = '<option value="">No projects</option>';
    return;
  }
  picker.innerHTML = '<option value="">-- Select project --</option>' +
    projects.map(p => `<option value="${p.id}">${p.name} (${p.id})</option>`).join('');

  picker.addEventListener('change', () => {
    currentProject = picker.value || null;
    if (currentProject) loadDashboard(currentProject);
  });

  // Auto-select first project
  if (projects.length > 0) {
    picker.value = projects[0].id;
    currentProject = projects[0].id;
    loadDashboard(currentProject);
  }
}

async function loadDashboard(projectId) {
  const content = document.getElementById('content');
  const [project, tasks, summary] = await Promise.all([
    fetchJSON(`/api/projects/${projectId}`),
    fetchJSON(`/api/projects/${projectId}/tasks`),
    fetchJSON(`/api/projects/${projectId}/summary`),
  ]);

  if (!project) { content.innerHTML = '<div class="empty"><h3>Project not found</h3></div>'; return; }

  let html = '';

  // Project info
  html += `<div class="project-info">
    <h2>${esc(project.name)}</h2>
    <div class="project-meta">
      Repo: <code>${esc(project.repo_path)}</code>
      &nbsp;&middot;&nbsp; Branch: <code>${esc(project.default_branch)}</code>
      ${project.slack_channel ? `&nbsp;&middot;&nbsp; Slack: <code>${esc(project.slack_channel)}</code>` : ''}
    </div>
  </div>`;

  // Summary
  if (summary) {
    const c = summary.counts;
    html += `<div class="summary">
      <span class="stat"><span class="dot todo"></span> ${c.todo} todo</span>
      <span class="stat"><span class="dot in-progress"></span> ${c['in-progress']} in progress</span>
      <span class="stat"><span class="dot done"></span> ${c.done} done</span>
      <span class="stat"><span class="dot blocked"></span> ${c.blocked} blocked</span>
      <div class="progress-bar"><div class="fill" style="width:${summary.progress_pct}%"></div></div>
      <span class="progress-pct">${summary.progress_pct}%</span>
    </div>`;
  }

  // Refresh bar
  html += `<div class="refresh-bar">
    <span>Tasks (${tasks ? tasks.length : 0} top-level)</span>
    <button onclick="loadDashboard('${projectId}')">Refresh</button>
  </div>`;

  // Tasks
  if (!tasks || tasks.length === 0) {
    html += '<div class="empty"><h3>No tasks yet</h3><p>Create tasks with <code>wo task add</code></p></div>';
  } else {
    html += '<div class="task-list">';
    for (const task of tasks) {
      html += renderTask(task, false);
      if (task.subtasks) {
        for (const sub of task.subtasks) {
          html += renderTask(sub, true);
        }
      }
    }
    html += '</div>';
  }

  content.innerHTML = html;
}

function renderTask(task, isSubtask) {
  const cls = isSubtask ? 'task-card subtask' : 'task-card';
  const statusCls = task.status.replace(' ', '-');
  let details = '';

  if (task.description) {
    details += `<div>${esc(task.description)}</div>`;
  }
  if (task.branch_name) {
    details += `<div>Branch: <code>${esc(task.branch_name)}</code></div>`;
  }
  if (task.worktree_path) {
    details += `<div>Worktree: <code>${esc(task.worktree_path)}</code></div>`;
  }
  if (task.pr_url) {
    details += `<div>PR: <a href="${esc(task.pr_url)}" target="_blank" rel="noopener">${esc(task.pr_url)}</a></div>`;
  }
  if (task.depends_on && task.depends_on.length > 0) {
    details += `<div class="dep-list">Depends on: ${task.depends_on.map(d => `<code>${esc(d)}</code>`).join(', ')}</div>`;
  }
  if (task.completed_at) {
    details += `<div>Completed: ${new Date(task.completed_at).toLocaleDateString()}</div>`;
  }

  return `<div class="${cls}">
    <div class="task-header">
      <span class="badge ${statusCls}">${esc(task.status)}</span>
      <span class="task-title">${esc(task.title)}</span>
      <span class="task-id">${esc(task.id)}</span>
    </div>
    ${details ? `<div class="task-details">${details}</div>` : ''}
  </div>`;
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Auto-refresh every 30s
function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    if (currentProject) loadDashboard(currentProject);
  }, 30000);
}

loadProjects();
startAutoRefresh();
</script>
</body>
</html>"""
