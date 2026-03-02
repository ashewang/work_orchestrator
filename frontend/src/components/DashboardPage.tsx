import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useProjects, useAgents, useProjectTasks, useProjectSummary } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import * as api from '../api/client';
import type { AgentRun, Project, Task } from '../types';

const STATUS_BADGE: Record<string, string> = {
  running: 'bg-blue-900 text-blue-300',
  completed: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
  cancelled: 'bg-gray-800 text-gray-500',
};

const TASK_STATUS_BADGE: Record<string, string> = {
  todo: 'bg-gray-700 text-gray-300',
  'in-progress': 'bg-blue-900 text-blue-300',
  review: 'bg-yellow-900 text-yellow-300',
  done: 'bg-green-900 text-green-300',
  blocked: 'bg-red-900 text-red-300',
};

function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ── Active Agents Panel ──────────────────────────────────────────────────

function ActiveAgents({ agents }: { agents: AgentRun[] }) {
  const running = agents.filter((a) => a.status === 'running');

  if (!running.length) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-6 text-center">
        <p className="text-sm text-gray-500">No agents running</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {running.map((a) => (
        <div
          key={a.id}
          className="rounded-lg border border-blue-800/50 bg-blue-950/30 p-4"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-blue-400" />
              <span className="text-sm font-medium text-blue-200">Running</span>
            </div>
            <span className="text-xs text-gray-500">{timeAgo(a.started_at)}</span>
          </div>
          <p className="mt-2 text-sm text-gray-300">Task: {a.task_id}</p>
          <p className="text-xs text-gray-500">
            {a.backend} / {a.model} &middot; PID {a.pid}
          </p>
        </div>
      ))}
    </div>
  );
}

// ── Recent Activity ──────────────────────────────────────────────────────

function RecentActivity({ agents }: { agents: AgentRun[] }) {
  const completed = agents
    .filter((a) => a.status !== 'running')
    .slice(0, 10);

  if (!completed.length) {
    return <p className="text-sm text-gray-500">No recent activity.</p>;
  }

  return (
    <div className="space-y-1">
      {completed.map((a) => (
        <div
          key={a.id}
          className="flex items-center justify-between rounded-lg bg-gray-900 px-4 py-2.5"
        >
          <div className="flex items-center gap-3 min-w-0">
            <span
              className={`rounded-full px-2 py-0.5 text-xs whitespace-nowrap ${STATUS_BADGE[a.status] || ''}`}
            >
              {a.status}
            </span>
            <span className="text-sm text-gray-300 truncate">{a.task_id}</span>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <span className="text-xs text-gray-500">{a.backend}/{a.model}</span>
            <span className="text-xs text-gray-600">{timeAgo(a.completed_at)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Dispatch Modal ───────────────────────────────────────────────────────

function DispatchPanel({
  projects,
  onClose,
}: {
  projects: Project[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '');
  const [selectedTask, setSelectedTask] = useState('');
  const [backend, setBackend] = useState('claude-code');
  const [dispatching, setDispatching] = useState(false);
  const [error, setError] = useState('');

  const { data: tasks } = useProjectTasks(selectedProject, 'todo');

  const handleDispatch = async () => {
    if (!selectedTask) return;
    setDispatching(true);
    setError('');
    try {
      await api.dispatchTask(selectedTask, { backend });
      queryClient.invalidateQueries({ queryKey: ['agents'] });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dispatch failed');
    } finally {
      setDispatching(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Dispatch Agent</h3>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-sm">
          Cancel
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Project</label>
          <select
            value={selectedProject}
            onChange={(e) => {
              setSelectedProject(e.target.value);
              setSelectedTask('');
            }}
            className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Task</label>
          <select
            value={selectedTask}
            onChange={(e) => setSelectedTask(e.target.value)}
            className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white"
          >
            <option value="">Select a task...</option>
            {tasks?.map((t: Task) => (
              <option key={t.id} value={t.id}>
                P{t.priority} — {t.title}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Backend</label>
          <select
            value={backend}
            onChange={(e) => setBackend(e.target.value)}
            className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white"
          >
            <option value="claude-code">Claude Code</option>
            <option value="opencode">OpenCode</option>
            <option value="pi">Pi Agent</option>
          </select>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <button
          onClick={handleDispatch}
          disabled={!selectedTask || dispatching}
          className="w-full rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
        >
          {dispatching ? 'Dispatching...' : 'Dispatch'}
        </button>
      </div>
    </div>
  );
}

// ── Main Dashboard ───────────────────────────────────────────────────────

export default function DashboardPage() {
  useWebSocket(); // Real-time updates + browser notifications
  const { data: projects } = useProjects();
  const { data: agents } = useAgents();
  const [showDispatch, setShowDispatch] = useState(false);

  const allAgents = agents || [];
  const runningCount = allAgents.filter((a) => a.status === 'running').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            {runningCount > 0
              ? `${runningCount} agent${runningCount > 1 ? 's' : ''} running`
              : 'All quiet'}
          </p>
        </div>
        <button
          onClick={() => setShowDispatch(!showDispatch)}
          className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500"
        >
          Dispatch Agent
        </button>
      </div>

      {/* Dispatch panel */}
      {showDispatch && projects?.length ? (
        <DispatchPanel projects={projects} onClose={() => setShowDispatch(false)} />
      ) : null}

      {/* Two-column layout */}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* Left: Activity */}
        <div className="space-y-6">
          <section>
            <h2 className="mb-3 text-lg font-semibold text-white">Active Agents</h2>
            <ActiveAgents agents={allAgents} />
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold text-white">Recent Activity</h2>
            <RecentActivity agents={allAgents} />
          </section>
        </div>

        {/* Right: Project summaries */}
        <div>
          <h2 className="mb-3 text-lg font-semibold text-white">Projects</h2>
          {!projects?.length ? (
            <p className="text-sm text-gray-500">
              No projects. Create one with <code className="text-gray-400">wo init &lt;name&gt;</code>
            </p>
          ) : (
            <div className="space-y-3">
              {projects.map((p) => (
                <ProjectSummaryCard key={p.id} project={p} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ProjectSummaryCard({ project }: { project: Project }) {
  const { data: summary } = useProjectSummary(project.id);

  const pct = summary?.progress_pct ?? 0;

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h3 className="font-medium text-white truncate">{project.name}</h3>
      {summary && summary.total > 0 ? (
        <>
          <div className="mt-2 flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-800">
              <div
                className="h-full rounded-full bg-green-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs text-gray-500">{pct}%</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(summary.counts).map(([status, count]) =>
              count > 0 ? (
                <span
                  key={status}
                  className={`rounded-full px-2 py-0.5 text-xs ${TASK_STATUS_BADGE[status] || 'bg-gray-800 text-gray-500'}`}
                >
                  {count} {status}
                </span>
              ) : null,
            )}
          </div>
        </>
      ) : (
        <p className="mt-1 text-xs text-gray-500">No tasks yet</p>
      )}
    </div>
  );
}
