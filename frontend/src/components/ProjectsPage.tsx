import { useState } from 'react';
import { useProjects, useProjectSummary, useProjectTasks } from '../hooks/useApi';
import type { Project } from '../types';
import TaskCard from './TaskCard';
import AgentMonitor from './AgentMonitor';
import WorktreePanel from './WorktreePanel';

const STATUSES = ['all', 'todo', 'in-progress', 'review', 'done', 'blocked'] as const;

function ProjectCard({ project }: { project: Project }) {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const { data: summary } = useProjectSummary(project.id);
  const statusParam = filter === 'all' ? undefined : filter;
  const { data: tasks, isLoading: tasksLoading } = useProjectTasks(
    expanded ? project.id : '',
    statusParam,
  );

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-5 py-4 text-left flex items-center justify-between gap-4 hover:bg-gray-800/50 transition"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            className={`text-xs text-gray-500 transition-transform ${expanded ? 'rotate-90' : ''}`}
          >
            &#9654;
          </span>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-white truncate">{project.name}</h2>
            {project.repo_path && (
              <p className="text-xs text-gray-500 truncate">{project.repo_path}</p>
            )}
          </div>
        </div>

        {summary && (
          <div className="flex items-center gap-4 flex-shrink-0">
            <div className="flex gap-2 text-xs">
              {Object.entries(summary.counts).map(([status, count]) =>
                count > 0 ? (
                  <span key={status} className="text-gray-500">
                    {count} {status}
                  </span>
                ) : null,
              )}
            </div>
            <div className="flex items-center gap-2 w-32">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-800">
                <div
                  className="h-full rounded-full bg-green-500 transition-all"
                  style={{ width: `${summary.progress_pct}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 w-8 text-right">
                {summary.progress_pct}%
              </span>
            </div>
          </div>
        )}
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-gray-800">
          {/* Status filter tabs */}
          <div className="flex gap-1 px-5 py-2 border-b border-gray-800">
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className={`rounded-full px-3 py-1 text-xs transition ${
                  filter === s
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Content: tasks on left, agents+worktrees on right */}
          <div className="grid gap-4 p-5 lg:grid-cols-[1fr_280px]">
            <div>
              {tasksLoading ? (
                <p className="text-sm text-gray-500">Loading tasks...</p>
              ) : !tasks?.length ? (
                <p className="text-sm text-gray-500">No tasks found.</p>
              ) : (
                <div className="space-y-3">
                  {tasks.map((t) => (
                    <TaskCard key={t.id} task={t} />
                  ))}
                </div>
              )}
            </div>
            <div className="space-y-4">
              <AgentMonitor projectId={project.id} />
              <WorktreePanel projectId={project.id} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProjectsPage() {
  const { data: projects, isLoading } = useProjects();

  if (isLoading) return <p className="text-gray-500">Loading projects...</p>;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-white">Projects</h1>
      {!projects?.length ? (
        <p className="text-gray-500">
          No projects found. Create one with: <code>wo init &lt;name&gt;</code>
        </p>
      ) : (
        <div className="space-y-4">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </div>
  );
}
