import { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useProjects, usePlanSessions, usePlanSession } from '../hooks/useApi';
import * as api from '../api/client';
import type { Task } from '../types';

const PHASE_LABELS: Record<string, string> = {
  brainstorm: 'Brainstorming',
  prd: 'PRD Review',
  decompose: 'Decomposing',
  approved: 'Approved',
  cancelled: 'Cancelled',
};

const PHASE_COLORS: Record<string, string> = {
  brainstorm: 'bg-purple-900/60 text-purple-300',
  prd: 'bg-blue-900/60 text-blue-300',
  decompose: 'bg-yellow-900/60 text-yellow-300',
  approved: 'bg-green-900/60 text-green-300',
  cancelled: 'bg-gray-800 text-gray-500',
};

// ── Date grouping helper ───────────────────────────────────────────────────

function getDateGroup(dateStr: string | null): string {
  if (!dateStr) return 'Older';
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return 'This week';
  return 'Older';
}

// ── Chat View ──────────────────────────────────────────────────────────────

function ChatView({ sessionId }: { sessionId: string }) {
  const { data: session, refetch } = usePlanSession(sessionId);
  const { data: projects } = useProjects();
  const queryClient = useQueryClient();
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState('');
  const [pendingTasks, setPendingTasks] = useState<Record<string, unknown>[] | null>(null);
  const [createdTasks, setCreatedTasks] = useState<Task[] | null>(null);
  const [dispatching, setDispatching] = useState<Set<string>>(new Set());
  const [dispatched, setDispatched] = useState<Set<string>>(new Set());
  const [approveProjectId, setApproveProjectId] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.messages, streamedText]);

  // Reset local state when switching sessions
  useEffect(() => {
    setPendingTasks(null);
    setCreatedTasks(null);
    setDispatching(new Set());
    setDispatched(new Set());
    setStreamedText('');
    setInput('');
    setApproveProjectId('');
  }, [sessionId]);

  // Pre-fill project picker from session or first project
  useEffect(() => {
    if (!approveProjectId) {
      if (session?.project_id) {
        setApproveProjectId(session.project_id);
      } else if (projects?.length === 1) {
        setApproveProjectId(projects[0].id);
      }
    }
  }, [session, projects, approveProjectId]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;
      setInput('');
      setStreaming(true);
      setStreamedText('');
      abortRef.current = false;

      // Auto-title: if this is the first message, update session title
      const isFirstMessage = !session?.messages?.length;

      try {
        let full = '';
        for await (const chunk of api.sendPlanMessage(sessionId, text)) {
          if (abortRef.current) break;
          full += chunk;
          setStreamedText(full);
        }
      } catch (err) {
        console.error('Stream error:', err);
      } finally {
        setStreaming(false);
        setStreamedText('');
        refetch();
        queryClient.invalidateQueries({ queryKey: ['planSessions'] });

        // Auto-title from first message
        if (isFirstMessage && text.trim()) {
          const autoTitle = text.trim().slice(0, 50) + (text.length > 50 ? '...' : '');
          api.updateSession(sessionId, { title: autoTitle }).catch(() => {});
          queryClient.invalidateQueries({ queryKey: ['planSessions'] });
        }
      }
    },
    [sessionId, streaming, session, refetch, queryClient],
  );

  const handleApprovePrd = async () => {
    await api.approvePrd(sessionId);
    refetch();
  };

  const handleDecompose = async () => {
    const result = await api.decomposePlan(sessionId);
    setPendingTasks(result.tasks);
    refetch();
  };

  const handleApprove = async () => {
    if (!pendingTasks || !approveProjectId) return;
    const result = await api.approvePlan(sessionId, pendingTasks, approveProjectId);
    setPendingTasks(null);
    setCreatedTasks(result.created);
    refetch();
    queryClient.invalidateQueries({ queryKey: ['tasks'] });
  };

  const handleDispatchTask = async (taskId: string) => {
    setDispatching((prev) => new Set(prev).add(taskId));
    try {
      await api.dispatchTask(taskId);
      setDispatched((prev) => new Set(prev).add(taskId));
      queryClient.invalidateQueries({ queryKey: ['agents'] });
    } catch (err) {
      console.error('Dispatch error:', err);
    } finally {
      setDispatching((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  };

  const handleDispatchAll = async () => {
    if (!createdTasks) return;
    const todoTasks = createdTasks.filter(
      (t) => t.status === 'todo' && !dispatched.has(t.id),
    );
    for (const task of todoTasks) {
      await handleDispatchTask(task.id);
    }
  };

  const messages = session?.messages || [];

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-gray-800 px-4 py-3">
        <h3 className="font-semibold text-white truncate">{session?.title || 'New chat'}</h3>
        {session && (
          <span
            className={`rounded-full px-2 py-0.5 text-xs whitespace-nowrap ${PHASE_COLORS[session.phase] || ''}`}
          >
            {PHASE_LABELS[session.phase] || session.phase}
          </span>
        )}
        <div className="ml-auto flex gap-2 flex-shrink-0">
          {session?.phase === 'brainstorm' && messages.length >= 2 && (
            <button
              onClick={handleApprovePrd}
              className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500"
            >
              Generate PRD
            </button>
          )}
          {session?.phase === 'prd' && (
            <button
              onClick={handleDecompose}
              className="rounded bg-yellow-600 px-3 py-1 text-xs text-white hover:bg-yellow-500"
            >
              Decompose into Tasks
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !streaming && (
          <div className="flex h-full items-center justify-center">
            <p className="text-gray-600 text-sm">Start typing to brainstorm...</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-lg px-4 py-3 text-sm ${
              m.role === 'user'
                ? 'ml-12 bg-blue-900/40 text-blue-100'
                : m.role === 'assistant'
                  ? 'mr-12 bg-gray-800 text-gray-200'
                  : 'bg-gray-900 text-gray-500 text-xs italic'
            }`}
          >
            <pre className="whitespace-pre-wrap font-sans">{m.content}</pre>
          </div>
        ))}

        {streaming && streamedText && (
          <div className="mr-12 rounded-lg bg-gray-800 px-4 py-3 text-sm text-gray-200">
            <pre className="whitespace-pre-wrap font-sans">{streamedText}</pre>
            <span className="inline-block h-3 w-1 animate-pulse bg-blue-400 ml-0.5" />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Pending tasks — with inline project picker */}
      {pendingTasks && (
        <div className="border-t border-gray-800 bg-gray-900/80 px-4 py-3">
          <p className="mb-2 text-sm font-medium text-yellow-400">
            {pendingTasks.length} tasks decomposed
          </p>
          <div className="max-h-40 overflow-y-auto space-y-1 mb-3">
            {pendingTasks.map((t, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-300">
                <span className="text-gray-500 w-5 text-right">{i + 1}.</span>
                <span className="truncate">{String(t.title || `Task ${i + 1}`)}</span>
                {t.priority != null && (
                  <span className="text-gray-600 flex-shrink-0">P{String(t.priority)}</span>
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-gray-400">Project:</label>
            <select
              value={approveProjectId}
              onChange={(e) => setApproveProjectId(e.target.value)}
              className="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-xs text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="">Select project...</option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <button
              onClick={handleApprove}
              disabled={!approveProjectId}
              className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-500 disabled:opacity-40"
            >
              Approve & Create Tasks
            </button>
          </div>
        </div>
      )}

      {/* Created tasks — with dispatch buttons */}
      {createdTasks && createdTasks.length > 0 && (
        <div className="border-t border-gray-800 bg-gray-900/80 px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-green-400">{createdTasks.length} tasks created</p>
            {createdTasks.some((t) => t.status === 'todo' && !dispatched.has(t.id)) && (
              <button
                onClick={handleDispatchAll}
                className="rounded bg-purple-600 px-3 py-1 text-xs text-white hover:bg-purple-500"
              >
                Dispatch All
              </button>
            )}
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {createdTasks.map((t) => (
              <div key={t.id} className="flex items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 text-gray-300 min-w-0">
                  <span className="font-mono text-gray-500">{t.id}</span>
                  <span className="truncate">{t.title}</span>
                </div>
                {dispatched.has(t.id) ? (
                  <span className="text-green-400 flex-shrink-0">dispatched</span>
                ) : (
                  <button
                    onClick={() => handleDispatchTask(t.id)}
                    disabled={dispatching.has(t.id)}
                    className="rounded bg-purple-700 px-2 py-0.5 text-white hover:bg-purple-600 disabled:opacity-50 flex-shrink-0"
                  >
                    {dispatching.has(t.id) ? '...' : 'Dispatch'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-gray-800 p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage(input);
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              session?.phase === 'approved'
                ? 'Plan approved — dispatch tasks above'
                : 'What do you want to build?'
            }
            disabled={streaming || session?.phase === 'approved'}
            className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
            autoFocus
          />
          <button
            type="submit"
            disabled={streaming || !input.trim() || session?.phase === 'approved'}
            className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {streaming ? '...' : 'Send'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { data: sessions } = usePlanSessions();
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();

  const handleNewChat = async () => {
    if (creating) return;
    setCreating(true);
    try {
      const session = await api.startPlanning();
      setActiveSession(session.id);
      queryClient.invalidateQueries({ queryKey: ['planSessions'] });
    } finally {
      setCreating(false);
    }
  };

  // Sort sessions by most recent first, then group by date
  const sortedSessions = [...(sessions || [])].sort((a, b) => {
    const da = a.updated_at || a.created_at || '';
    const db_ = b.updated_at || b.created_at || '';
    return db_.localeCompare(da);
  });

  // Group by date
  const groups: { label: string; items: typeof sortedSessions }[] = [];
  const groupOrder = ['Today', 'Yesterday', 'This week', 'Older'];
  const grouped: Record<string, typeof sortedSessions> = {};
  for (const s of sortedSessions) {
    const g = getDateGroup(s.updated_at || s.created_at);
    (grouped[g] ||= []).push(s);
  }
  for (const label of groupOrder) {
    if (grouped[label]?.length) {
      groups.push({ label, items: grouped[label] });
    }
  }

  return (
    <div className="flex h-[calc(100vh-5rem)]">
      {/* Sidebar */}
      <div className="w-64 flex-shrink-0 border-r border-gray-800 flex flex-col bg-gray-950">
        <div className="p-3">
          <button
            onClick={handleNewChat}
            disabled={creating}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition disabled:opacity-50"
          >
            + New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {groups.length === 0 && (
            <p className="text-xs text-gray-600 px-2 py-4 text-center">No chats yet</p>
          )}
          {groups.map((group) => (
            <div key={group.label} className="mb-3">
              <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
                {group.label}
              </p>
              {group.items.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setActiveSession(s.id)}
                  className={`w-full rounded px-3 py-2 text-left transition ${
                    s.id === activeSession
                      ? 'bg-gray-800 text-white'
                      : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
                  }`}
                >
                  <span className="block truncate text-sm">{s.title}</span>
                  <span
                    className={`mt-0.5 inline-block rounded-full px-1.5 py-0 text-[10px] ${PHASE_COLORS[s.phase] || 'bg-gray-800 text-gray-500'}`}
                  >
                    {PHASE_LABELS[s.phase] || s.phase}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 overflow-hidden bg-gray-900">
        {activeSession ? (
          <ChatView sessionId={activeSession} />
        ) : (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <p className="text-lg text-gray-400">Start a new chat</p>
              <p className="mt-1 text-sm text-gray-600">
                Brainstorm, plan, decompose into tasks, dispatch agents
              </p>
              <button
                onClick={handleNewChat}
                disabled={creating}
                className="mt-4 rounded-lg bg-blue-600 px-5 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
              >
                + New Chat
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
