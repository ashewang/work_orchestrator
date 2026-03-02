import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export interface WsEvent {
  type: string;
  task_id?: string;
  task_title?: string;
  agent_status?: string;
  [key: string]: unknown;
}

export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const event: WsEvent = JSON.parse(e.data);

        // Invalidate relevant queries so dashboard auto-refreshes
        if (event.type === 'agent_completed') {
          queryClient.invalidateQueries({ queryKey: ['agents'] });
          queryClient.invalidateQueries({ queryKey: ['tasks'] });
          queryClient.invalidateQueries({ queryKey: ['summary'] });

          // Browser notification
          if (Notification.permission === 'granted') {
            const status = event.agent_status === 'completed' ? 'completed' : 'failed';
            new Notification(`Agent ${status}`, {
              body: event.task_title || event.task_id || 'Unknown task',
              tag: `agent-${event.task_id}`,
            });
          }
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      // Reconnect after 3 seconds
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [queryClient]);

  useEffect(() => {
    // Request notification permission on mount
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
