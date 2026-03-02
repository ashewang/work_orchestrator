import type { Project, Task, ProjectSummary, AgentRun, WorktreeSlot, PlanningSession } from '../types';

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

// Planning
export const startPlanning = (title?: string, projectId?: string) =>
  fetchJSON<PlanningSession>('/plan/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, project_id: projectId }),
  });

export const updateSession = (sessionId: string, updates: { title?: string; project_id?: string }) =>
  fetchJSON<PlanningSession>(`/plan/${sessionId}/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });

export const sendPlanMessage = async function* (sessionId: string, message: string) {
  const res = await fetch(`${BASE}/plan/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ') && line !== 'data: [DONE]') {
        try {
          const data = JSON.parse(line.slice(6));
          yield data.text as string;
        } catch { /* skip */ }
      }
    }
  }
};

export const approvePrd = (sessionId: string) =>
  fetchJSON<{ prd: string; session: PlanningSession }>(`/plan/${sessionId}/approve-prd`, {
    method: 'POST',
  });

export const decomposePlan = (sessionId: string) =>
  fetchJSON<{ tasks: Record<string, unknown>[]; count: number }>(`/plan/${sessionId}/decompose`, {
    method: 'POST',
  });

export const approvePlan = (sessionId: string, tasks: Record<string, unknown>[], projectId?: string) =>
  fetchJSON<{ created: Task[]; count: number }>(`/plan/${sessionId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tasks, project_id: projectId }),
  });

export const getPlanSessions = (projectId?: string) => {
  const qs = projectId ? `?project_id=${projectId}` : '';
  return fetchJSON<PlanningSession[]>(`/plan/sessions${qs}`);
};

export const getPlanSession = (sessionId: string) =>
  fetchJSON<PlanningSession>(`/plan/${sessionId}`);

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
