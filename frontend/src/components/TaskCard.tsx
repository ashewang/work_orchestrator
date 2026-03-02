import type { Task } from '../types';

const STATUS_COLORS: Record<string, string> = {
  todo: 'bg-gray-700 text-gray-300',
  'in-progress': 'bg-blue-900 text-blue-300',
  done: 'bg-green-900 text-green-300',
  blocked: 'bg-red-900 text-red-300',
  review: 'bg-yellow-900 text-yellow-300',
};

const PRIORITY_COLORS: Record<number, string> = {
  0: 'text-red-400',
  1: 'text-orange-400',
  2: 'text-yellow-400',
  3: 'text-gray-400',
  4: 'text-gray-500',
  5: 'text-gray-600',
  6: 'text-gray-700',
};

export default function TaskCard({ task }: { task: Task }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-medium text-gray-100">{task.title}</h3>
          <p className="mt-1 text-xs text-gray-500">{task.id}</p>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_COLORS[task.status] || 'bg-gray-700'}`}>
          {task.status}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <span className={`font-mono font-bold ${PRIORITY_COLORS[task.priority] || 'text-gray-400'}`}>
          P{task.priority}
        </span>
        {task.branch_name && (
          <span className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-400">
            {task.branch_name}
          </span>
        )}
        {task.pr_url && (
          <a
            href={task.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            PR
          </a>
        )}
      </div>

      {task.depends_on.length > 0 && (
        <p className="mt-2 text-xs text-gray-500">
          Depends on: {task.depends_on.join(', ')}
        </p>
      )}

      {task.description && (
        <p className="mt-2 line-clamp-2 text-sm text-gray-400">{task.description}</p>
      )}

      {task.subtasks && task.subtasks.length > 0 && (
        <div className="mt-3 space-y-1 border-t border-gray-800 pt-2">
          {task.subtasks.map((sub) => (
            <div key={sub.id} className="flex items-center gap-2 text-xs text-gray-500">
              <span className={`h-1.5 w-1.5 rounded-full ${sub.status === 'done' ? 'bg-green-500' : 'bg-gray-600'}`} />
              {sub.title}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
