import { useSlots } from '../hooks/useApi';

const STATUS_COLORS: Record<string, string> = {
  available: 'bg-green-900 text-green-400',
  occupied: 'bg-yellow-900 text-yellow-400',
  draining: 'bg-orange-900 text-orange-400',
};

export default function WorktreePanel({ projectId }: { projectId: string }) {
  const { data: slots, isLoading } = useSlots(projectId);

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-white">Worktree Slots</h2>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading...</p>
      ) : !slots?.length ? (
        <p className="text-sm text-gray-500">No slots registered.</p>
      ) : (
        <div className="space-y-2">
          {slots.map((slot) => (
            <div
              key={slot.id}
              className="rounded-lg border border-gray-800 bg-gray-900 p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-200">
                  {slot.label}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs ${STATUS_COLORS[slot.status] || ''}`}
                >
                  {slot.status}
                </span>
              </div>
              {slot.branch && (
                <p className="mt-1 text-xs text-gray-500">{slot.branch}</p>
              )}
              {slot.current_task_id && (
                <p className="mt-1 text-xs text-blue-400">
                  Task: {slot.current_task_id}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
