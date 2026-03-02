import { useAgents } from '../hooks/useApi';

export default function AgentMonitor({ projectId }: { projectId?: string }) {
  const { data: agents, isLoading } = useAgents(undefined, projectId);

  const running = agents?.filter((a) => a.status === 'running') || [];
  const recent = agents?.filter((a) => a.status !== 'running').slice(0, 5) || [];

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-white">Agents</h2>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading...</p>
      ) : (
        <div className="space-y-2">
          {running.length > 0 && (
            <div className="space-y-2">
              {running.map((a) => (
                <div
                  key={a.id}
                  className="rounded-lg border border-blue-800 bg-blue-950 p-3"
                >
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-blue-400" />
                    <span className="text-sm font-medium text-blue-300">Running</span>
                  </div>
                  <p className="mt-1 text-xs text-gray-400">
                    Task: {a.task_id} | PID: {a.pid}
                  </p>
                  <p className="text-xs text-gray-500">
                    {a.backend} / {a.model}
                  </p>
                </div>
              ))}
            </div>
          )}

          {recent.length > 0 && (
            <div className="space-y-1">
              {recent.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between rounded bg-gray-900 px-3 py-2 text-xs"
                >
                  <span className="text-gray-400">{a.task_id}</span>
                  <span
                    className={
                      a.status === 'completed'
                        ? 'text-green-400'
                        : a.status === 'failed'
                          ? 'text-red-400'
                          : 'text-gray-500'
                    }
                  >
                    {a.status}
                  </span>
                </div>
              ))}
            </div>
          )}

          {!running.length && !recent.length && (
            <p className="text-sm text-gray-500">No agent runs.</p>
          )}
        </div>
      )}
    </div>
  );
}
