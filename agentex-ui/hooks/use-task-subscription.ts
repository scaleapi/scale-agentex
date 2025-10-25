import { useEffect } from 'react';

import { useQueryClient } from '@tanstack/react-query';
import { subscribeTaskState } from 'agentex/lib';

import { taskMessagesKeys } from './use-task-messages';
import { tasksKeys } from './use-tasks';

import type AgentexSDK from 'agentex';
import type { Task } from 'agentex/resources';

/**
 * Subscribes to real-time task state updates via WebSocket/SSE
 * and syncs them directly to React Query cache
 */
export function useTaskSubscription({
  agentexClient,
  taskId,
  enabled = true,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
  enabled?: boolean;
}) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled || !taskId) return;

    const abortController = new AbortController();

    // Start the subscription (it's async but we don't await in useEffect)
    subscribeTaskState(
      agentexClient,
      { taskID: taskId },
      {
        onMessagesChange(messages) {
          queryClient.setQueryData(taskMessagesKeys.byTaskId(taskId), {
            messages: [...messages],
            deltaAccumulator: null,
          });

          // Check if any messages are still streaming
          const hasStreamingMessages = messages.some(
            msg => msg.streaming_status === 'IN_PROGRESS'
          );

          // If no messages are streaming, invalidate spans to fetch latest traces
          if (!hasStreamingMessages && messages.length > 0) {
            queryClient.invalidateQueries({ queryKey: ['spans', taskId] });
          }
        },
        onAgentsChange() {
          // Agent changes handled by separate query
        },
        onTaskChange(task) {
          // Update the specific task in the cache
          queryClient.setQueryData<Task>(tasksKeys.byId(taskId), task);

          // Also update it in the tasks list
          queryClient.setQueryData<Task[]>(tasksKeys.all, old => {
            if (!old) return [task];
            return old.map(t => (t.id === task.id ? task : t));
          });
        },
        onStreamStatusChange(status) {
          queryClient.setQueryData(['streamStatus', taskId], status);
        },
        onError(errorMessage) {
          console.error('Task subscription error:', errorMessage);
          queryClient.setQueryData(['streamStatus', taskId], 'error');
        },
      },
      { signal: abortController.signal }
    );

    return () => {
      abortController.abort();
    };
  }, [agentexClient, taskId, enabled, queryClient]);
}

/**
 * Get the current WebSocket connection status for a task
 * Returns 'connected', 'reconnecting', 'disconnected', or 'error'
 */
export function useStreamStatus(taskId: string) {
  const queryClient = useQueryClient();

  return (
    queryClient.getQueryData<
      'connected' | 'reconnecting' | 'disconnected' | 'error'
    >(['streamStatus', taskId]) ?? 'connected'
  );
}
