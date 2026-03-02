export interface Project {
  id: string;
  name: string;
  repo_path: string;
  default_branch: string;
  slack_channel: string | null;
  created_at: string | null;
}

export interface Task {
  id: string;
  title: string;
  status: 'todo' | 'in-progress' | 'done' | 'blocked' | 'review';
  priority: number;
  description: string;
  project_id: string;
  parent_task_id: string | null;
  branch_name: string | null;
  worktree_path: string | null;
  pr_url: string | null;
  depends_on: string[];
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
  subtasks?: Task[];
}

export interface ProjectSummary {
  project_id: string;
  counts: Record<string, number>;
  total: number;
  progress_pct: number;
}

export interface AgentRun {
  id: number;
  task_id: string;
  pid: number;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  model: string;
  backend: string;
  started_at: string | null;
  completed_at?: string | null;
  exit_code?: number | null;
  result_summary?: string | null;
}

export interface WorktreeSlot {
  id: number;
  project_id: string;
  path: string;
  label: string;
  status: 'available' | 'occupied' | 'draining';
  branch?: string;
  current_task_id?: string;
}

export interface PlanningSession {
  id: string;
  project_id: string | null;
  title: string;
  phase: 'brainstorm' | 'prd' | 'decompose' | 'approved' | 'cancelled';
  created_at: string | null;
  updated_at: string | null;
  prd_content?: string;
  messages?: PlanningMessage[];
}

export interface PlanningMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string | null;
}
