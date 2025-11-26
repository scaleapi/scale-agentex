import { useEffect } from 'react';

import { InfiniteData, useQueryClient } from '@tanstack/react-query';
// import { subscribeTaskState } from 'agentex/lib';

import { updateTaskInInfiniteQuery } from '@/hooks/use-create-task';
import { taskMessagesKeys } from '@/hooks/use-task-messages';
import type { TaskMessagesData } from '@/hooks/use-task-messages';
import { tasksKeys } from '@/hooks/use-tasks';

import { subscribeTaskState } from './custom-subscribe-task-state';

import type AgentexSDK from 'agentex';
import type { TaskListResponse, TaskRetrieveResponse } from 'agentex/resources';

/**
 * Subscribes to real-time updates for a task's state, messages, and streaming status.
 *
 * Establishes a persistent connection to the Agentex backend to receive live task updates
 * as they happen. Automatically updates React Query cache when events arrive, triggering
 * UI re-renders. The subscription cleans up automatically on unmount or when dependencies change.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to establish the subscription connection
 * @param taskId - string - The unique ID of the task to monitor
 * @param agentName - string - The name of the agent executing the task (used for cache updates)
 * @param enabled - boolean - Whether the subscription should be active (default: true), should be false for sync agents
 * @returns void - This hook manages side effects and does not return a value
 */
export function useTaskSubscription({
  agentexClient,
  taskId,
  agentName,
  enabled = true,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
  agentName: string;
  enabled?: boolean;
}) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled || !taskId) return;

    const abortController = new AbortController();

    subscribeTaskState(
      agentexClient,
      { taskID: taskId },
      {
        onMessagesChange(messages) {
          queryClient.setQueryData<TaskMessagesData>(
            taskMessagesKeys.byTaskId(taskId),
            {
              messages: [...messages],
              deltaAccumulator: null,
              rpcStatus: 'pending',
            }
          );

          const hasStreamingMessages = messages.some(
            msg => msg.streaming_status === 'IN_PROGRESS'
          );

          if (!hasStreamingMessages && messages.length > 0) {
            queryClient.setQueryData<TaskMessagesData>(
              taskMessagesKeys.byTaskId(taskId),
              data => ({
                messages: data?.messages || [],
                deltaAccumulator: data?.deltaAccumulator || null,
                rpcStatus: 'success',
              })
            );
            queryClient.invalidateQueries({ queryKey: ['spans', taskId] });
          }
        },
        onAgentsChange() {},
        onTaskChange(task) {
          queryClient.setQueryData<TaskRetrieveResponse>(
            tasksKeys.individualById(taskId),
            task
          );
          queryClient.setQueryData<InfiniteData<TaskListResponse>>(
            tasksKeys.all,
            data => updateTaskInInfiniteQuery(task, agentName, data)
          );
          queryClient.setQueryData<InfiniteData<TaskListResponse>>(
            tasksKeys.byAgentName(agentName),
            data => updateTaskInInfiniteQuery(task, agentName, data)
          );
        },
        onStreamStatusChange() {},
        onError() {
          queryClient.setQueryData<TaskMessagesData>(
            taskMessagesKeys.byTaskId(taskId),
            data => ({
              messages: data?.messages || [],
              deltaAccumulator: data?.deltaAccumulator || null,
              rpcStatus: 'error',
            })
          );
        },
      },
      { signal: abortController.signal }
    );

    return () => {
      abortController.abort();
    };
  }, [agentexClient, taskId, enabled, queryClient, agentName]);
}
