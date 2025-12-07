import { useEffect } from 'react';

import { InfiniteData, useQueryClient } from '@tanstack/react-query';
import { subscribeTaskState } from 'agentex/lib';

import { updateTaskInInfiniteQuery } from '@/hooks/use-create-task';
import {
  infiniteTaskMessagesKeys,
  PaginatedMessagesResponse,
} from '@/hooks/use-infinite-task-messages';
import { tasksKeys } from '@/hooks/use-tasks';

import type AgentexSDK from 'agentex';
import type {
  TaskListResponse,
  TaskMessage,
  TaskRetrieveResponse,
} from 'agentex/resources';

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
          // Guard against undefined messages from SDK
          if (!messages || !Array.isArray(messages)) {
            return;
          }

          // Update the infinite query cache with real-time messages
          // Messages from SDK come in chronological order (oldest first)
          // We need to convert to API format (newest first) for the first page
          const newestFirstMessages = [...messages].reverse();

          queryClient.setQueryData<
            InfiniteData<PaginatedMessagesResponse, string | undefined>
          >(infiniteTaskMessagesKeys.byTaskId(taskId), oldData => {
            if (!oldData) {
              // Don't initialize cache from subscription - the SDK doesn't pass
              // pagination metadata (has_more, next_cursor), so we'd incorrectly
              // set has_more: false even when more messages exist.
              // Let useInfiniteTaskMessages handle initial fetch with proper metadata.
              return undefined;
            }

            // Get IDs of all messages from older pages (not the first page)
            const olderPageMessageIds = new Set(
              oldData.pages.slice(1).flatMap(page => page.data.map(m => m.id))
            );

            // Filter out messages that are already in older pages
            // to avoid duplicates when combining real-time with paginated data
            const newFirstPageMessages = newestFirstMessages.filter(
              m => !olderPageMessageIds.has(m.id)
            );

            return {
              ...oldData,
              pages: [
                {
                  ...oldData.pages[0],
                  data: newFirstPageMessages,
                } as PaginatedMessagesResponse,
                ...oldData.pages.slice(1),
              ],
            };
          });

          const hasStreamingMessages = messages.some(
            (msg: TaskMessage) => msg.streaming_status === 'IN_PROGRESS'
          );

          if (!hasStreamingMessages && messages.length > 0) {
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
          // Error handling - we don't need to update query cache on error
          // The UI will show the last known good state
          console.error('Task subscription error for task:', taskId);
        },
      },
      { signal: abortController.signal }
    );

    return () => {
      abortController.abort();
    };
  }, [agentexClient, taskId, enabled, queryClient, agentName]);
}
