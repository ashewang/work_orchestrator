import type { Project, Task, ProjectSummary, AgentRun, WorktreeSlot } from '../types';

const BASE = '/api';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// Projects
export const getProjects = () => fetchJSON<Project[]>('/projects');
export const getProject = (id: string) => fetchJSON<Project>(`/projects/${id}`);
export const getProjectTasks = (projectId: string, status?: string) => {
  const qs = status ? `?status=${status}` : '';
  return fetchJSON<Task[]>(`/projects/${projectId}/tasks${qs}`);
};
export const getProjectSummary = (projectId: string) =>
  fetchJSON<ProjectSummary>(`/projects/${projectId}/summary`);

// Tasks
export const getTask = (taskId: string) => fetchJSON<Task>(`/tasks/${taskId}`);

// Agents
export const getAgents = (status?: string, project?: string) => {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (project) params.set('project', project);
  const qs = params.toString() ? `?${params}` : '';
  return fetchJSON<AgentRun[]>(`/agents${qs}`);
};

// Worktree slots
export const getSlots = (projectId: string) =>
  fetchJSON<WorktreeSlot[]>(`/projects/${projectId}/slots`);


// Dispatch
export const dispatchTask = (
  taskId: string,
  options?: { backend?: string; model?: string; max_turns?: number },
) =>
  fetchJSON<AgentRun>(`/tasks/${taskId}/dispatch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
