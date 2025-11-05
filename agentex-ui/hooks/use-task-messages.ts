import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  agentRPCNonStreaming,
  agentRPCWithStreaming,
  aggregateMessageEvents,
} from 'agentex/lib';
import { v4 } from 'uuid';

import { toast } from '@/components/ui/toast';
import { agentsKeys } from '@/hooks/use-agents';

import type AgentexSDK from 'agentex';
import type { IDeltaAccumulator } from 'agentex/lib';
import type { Agent, TaskMessage, TaskMessageContent } from 'agentex/resources';

export type TaskMessagesData = {
  messages: TaskMessage[];
  deltaAccumulator: IDeltaAccumulator | null;
  rpcStatus: 'idle' | 'pending' | 'success' | 'error';
};

export const taskMessagesKeys = {
  all: ['taskMessages'] as const,
  byTaskId: (taskId: string) => [...taskMessagesKeys.all, taskId] as const,
};

/**
 * Fetches the conversation messages for a specific task.
 *
 * Returns all messages exchanged between the user and agent during task execution,
 * along with a delta accumulator for handling partial streaming updates and an RPC
 * status indicator. Refetching is disabled to prevent interrupting live message streams.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to fetch messages
 * @param taskId - string - The unique ID of the task whose messages to retrieve
 * @returns UseQueryResult<TaskMessagesData> - Query result containing messages, delta accumulator, and RPC status
 */
export function useTaskMessages({
  agentexClient,
  taskId,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
}) {
  return useQuery({
    queryKey: taskMessagesKeys.byTaskId(taskId),
    queryFn: async (): Promise<TaskMessagesData> => {
      if (!taskId) {
        return { messages: [], deltaAccumulator: null, rpcStatus: 'idle' };
      }

      const messages = await agentexClient.messages.list({
        task_id: taskId,
      });

      return {
        messages,
        deltaAccumulator: null,
        rpcStatus: 'idle',
      };
    },
    enabled: !!taskId,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

type SendMessageParams = {
  taskId: string;
  agentName: string;
  content: TaskMessageContent;
};

export function useSendMessage({
  agentexClient,
}: {
  agentexClient: AgentexSDK;
}) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ taskId, agentName, content }: SendMessageParams) => {
      const queryKey = taskMessagesKeys.byTaskId(taskId);

      const agents = queryClient.getQueryData<Agent[]>(agentsKeys.all) || [];
      const agent = agents.find(a => a.name === agentName);

      if (!agent) {
        throw new Error(`Agent with name ${agentName} not found`);
      }

      switch (agent.acp_type) {
        case 'async':
        case 'agentic': {
          queryClient.setQueryData<TaskMessagesData>(queryKey, data => ({
            messages: data?.messages || [],
            deltaAccumulator: data?.deltaAccumulator || null,
            rpcStatus: 'pending',
          }));

          const response = await agentRPCNonStreaming(
            agentexClient,
            { agentName },
            'event/send',
            { task_id: taskId, content }
          );

          if (response.error != null) {
            queryClient.setQueryData<TaskMessagesData>(queryKey, data => ({
              messages: data?.messages || [],
              deltaAccumulator: data?.deltaAccumulator || null,
              rpcStatus: 'error',
            }));
            throw new Error(response.error.message);
          }

          queryClient.setQueryData<TaskMessagesData>(queryKey, data => ({
            messages: data?.messages || [],
            deltaAccumulator: data?.deltaAccumulator || null,
            rpcStatus: 'pending',
          }));

          return (
            queryClient.getQueryData<TaskMessagesData>(queryKey) || {
              messages: [],
              deltaAccumulator: null,
              rpcStatus: 'pending',
            }
          );
        }

        case 'sync': {
          const currentData = queryClient.getQueryData<TaskMessagesData>(
            queryKey
          ) || {
            messages: [],
            deltaAccumulator: null,
            rpcStatus: 'pending',
          };

          const tempUserMessage: TaskMessage = {
            id: v4(),
            content,
            task_id: taskId,
            created_at: new Date().toISOString(),
            streaming_status: 'DONE',
            updated_at: new Date().toISOString(),
          };

          let latestMessages = [...currentData.messages, tempUserMessage];
          let latestDeltaAccumulator = currentData.deltaAccumulator;

          queryClient.setQueryData<TaskMessagesData>(queryKey, {
            messages: latestMessages,
            deltaAccumulator: latestDeltaAccumulator,
            rpcStatus: 'pending',
          });

          const controller = new AbortController();

          for await (const response of agentRPCWithStreaming(
            agentexClient,
            { agentName },
            'message/send',
            { task_id: taskId, content },
            { signal: controller.signal }
          )) {
            if (response.error != null) {
              queryClient.setQueryData<TaskMessagesData>(queryKey, data => ({
                messages: data?.messages || [],
                deltaAccumulator: data?.deltaAccumulator || null,
                rpcStatus: 'error',
              }));
              throw new Error(response.error.message);
            }

            const cacheData =
              queryClient.getQueryData<TaskMessagesData>(queryKey);
            if (cacheData) {
              latestMessages = cacheData.messages;
              latestDeltaAccumulator = cacheData.deltaAccumulator;
            }

            const result = aggregateMessageEvents(
              latestMessages,
              latestDeltaAccumulator,
              [response.result]
            );

            latestMessages = result.messages;
            latestDeltaAccumulator = result.deltaAccumulator;

            queryClient.setQueryData<TaskMessagesData>(queryKey, {
              messages: latestMessages,
              deltaAccumulator: latestDeltaAccumulator,
              rpcStatus: 'pending',
            });

            if (response.result.type === 'done') {
              queryClient.invalidateQueries({ queryKey: ['spans', taskId] });
            }
          }

          const finalMessages = await agentexClient.messages.list({
            task_id: taskId,
          });

          queryClient.setQueryData<TaskMessagesData>(queryKey, {
            messages: finalMessages,
            deltaAccumulator: null,
            rpcStatus: 'success',
          });

          return {
            messages: finalMessages,
            deltaAccumulator: null,
          };
        }

        default: {
          throw new Error(
            `Unsupported agent acp_type: ${(agent as Agent).acp_type}`
          );
        }
      }
    },
    onError: error => {
      toast.error({
        title: 'Failed to send message',
        message: error instanceof Error ? error.message : 'Please try again.',
      });
    },
  });
}
