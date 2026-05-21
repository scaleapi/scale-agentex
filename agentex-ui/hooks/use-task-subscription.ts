import { useEffect } from 'react';

import { InfiniteData, useQueryClient } from '@tanstack/react-query';

import { subscribeTaskState } from '@/hooks/custom-subscribe-task-state';
import { updateTaskInInfiniteQuery } from '@/hooks/use-create-task';
import {
  taskMessagesKeys,
  taskMessagesMetaKeys,
} from '@/hooks/use-task-messages';
import type { TaskMessagesMetadata } from '@/hooks/use-task-messages';
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
 * Merges subscription messages into the infinite query cache by ID rather than
 * overwriting, so already-fetched older pages are preserved.
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
          const queryKey = taskMessagesKeys.byTaskId(taskId);
          const metaKey = taskMessagesMetaKeys.byTaskId(taskId);

          // Merge subscription messages into infinite query pages by ID.
          // Subscription only knows about the newest messages — preserve older pages.
          queryClient.setQueryData<InfiniteData<TaskMessage[]>>(
            queryKey,
            oldData => {
              if (!oldData) {
                return { pages: [[...messages]], pageParams: [1] };
              }

              // Build a map of subscription messages by ID for lookup
              const subMessageMap = new Map<string, TaskMessage>();
              for (const m of messages) {
                if (m.id) subMessageMap.set(m.id, m);
              }

              // Update existing messages in all pages; track which IDs we matched
              const matchedIds = new Set<string>();
              const updatedPages = oldData.pages.map(page =>
                page.map(msg => {
                  if (msg.id && subMessageMap.has(msg.id)) {
                    matchedIds.add(msg.id);
                    return { ...subMessageMap.get(msg.id)! };
                  }
                  return msg;
                })
              );

              // Any unmatched subscription messages are NEW — append to first page
              const newMessages: TaskMessage[] = [];
              for (const m of messages) {
                if (m.id && !matchedIds.has(m.id)) {
                  newMessages.push(m);
                }
              }

              if (newMessages.length > 0) {
                updatedPages[0] = [...(updatedPages[0] ?? []), ...newMessages];
              }

              return { pages: updatedPages, pageParams: oldData.pageParams };
            }
          );

          const hasStreamingMessages = messages.some(
            msg => msg.streaming_status === 'IN_PROGRESS'
          );

          queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
            deltaAccumulator: null,
            rpcStatus: hasStreamingMessages ? 'pending' : 'success',
          });

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
          queryClient.setQueryData<TaskMessagesMetadata>(
            taskMessagesMetaKeys.byTaskId(taskId),
            {
              deltaAccumulator: null,
              rpcStatus: 'error',
            }
          );
        },
      },
      {
        signal: abortController.signal,
        getCachedMessages: () => {
          const data = queryClient.getQueryData<InfiniteData<TaskMessage[]>>(
            taskMessagesKeys.byTaskId(taskId)
          );
          if (!data?.pages?.length) return null;
          // Flatten all pages to chronological order for the subscription's local state
          return [...data.pages].reverse().flat();
        },
      }
    );

    return () => {
      abortController.abort();
    };
  }, [agentexClient, taskId, enabled, queryClient, agentName]);
}
