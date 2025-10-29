import { useEffect } from 'react';

import { useQueryClient } from '@tanstack/react-query';
import { subscribeTaskState } from 'agentex/lib';

import { taskMessagesKeys } from './use-task-messages';
import { tasksKeys } from './use-tasks';

import type { TaskMessagesData } from './use-task-messages';
import type AgentexSDK from 'agentex';
import type { Task } from 'agentex/resources';

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
          queryClient.setQueryData<Task>(tasksKeys.byId(taskId), task);
          queryClient.setQueryData<Task[]>(tasksKeys.all, old => {
            if (!old) return [task];
            return old.map(t => (t.id === task.id ? task : t));
          });
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
  }, [agentexClient, taskId, enabled, queryClient]);
}
