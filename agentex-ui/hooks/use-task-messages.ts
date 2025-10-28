import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  agentRPCNonStreaming,
  agentRPCWithStreaming,
  aggregateMessageEvents,
} from 'agentex/lib';
import { v4 } from 'uuid';

import { toast } from '@/components/agentex/toast';

import { agentsKeys } from './use-agents';

import type AgentexSDK from 'agentex';
import type { IDeltaAccumulator } from 'agentex/lib';
import type { Agent, TaskMessage, TaskMessageContent } from 'agentex/resources';

type TaskMessagesData = {
  messages: TaskMessage[];
  deltaAccumulator: IDeltaAccumulator | null;
};

/**
 * Query key factory for task messages
 */
export const taskMessagesKeys = {
  all: ['taskMessages'] as const,
  byTaskId: (taskId: string) => [...taskMessagesKeys.all, taskId] as const,
};

/**
 * Hook to fetch and cache messages for a specific task
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
        return { messages: [], deltaAccumulator: null };
      }

      // Fetch existing messages from the backend
      const messages = await agentexClient.messages.list({
        task_id: taskId,
      });

      return {
        messages,
        deltaAccumulator: null,
      };
    },
    enabled: !!taskId,
    staleTime: Infinity, // Messages don't change unless we update them
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

type SendMessageParams = {
  taskId: string;
  agentName: string;
  content: TaskMessageContent;
};

/**
 * Mutation hook to send a message and stream the response
 * Updates the React Query cache during streaming
 */
export function useSendMessage({
  agentexClient,
}: {
  agentexClient: AgentexSDK;
}) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ taskId, agentName, content }: SendMessageParams) => {
      const queryKey = taskMessagesKeys.byTaskId(taskId);

      // Get the agent to determine communication pattern
      const agents = queryClient.getQueryData<Agent[]>(agentsKeys.all) || [];
      const agent = agents.find(a => a.name === agentName);

      if (!agent) {
        throw new Error(`Agent with name ${agentName} not found`);
      }

      // Route message handling based on agent communication pattern
      switch (agent.acp_type) {
        case 'agentic': {
          // Fire-and-forget pattern: send event, agent handles async response
          // The SSE subscription will receive the response and update the cache
          const response = await agentRPCNonStreaming(
            agentexClient,
            { agentName },
            'event/send',
            { task_id: taskId, content }
          );

          if (response.error != null) {
            throw new Error(response.error.message);
          }

          // For agentic agents, we don't optimistically update or stream
          // The subscribeTaskState SSE connection will handle updates
          return (
            queryClient.getQueryData<TaskMessagesData>(queryKey) || {
              messages: [],
              deltaAccumulator: null,
            }
          );
        }

        case 'sync': {
          // Streaming pattern: immediate response with real-time updates
          const currentData = queryClient.getQueryData<TaskMessagesData>(
            queryKey
          ) || {
            messages: [],
            deltaAccumulator: null,
          };

          // Create temporary user message for optimistic UI
          const tempUserMessage: TaskMessage = {
            id: v4(),
            content,
            task_id: taskId,
            created_at: new Date().toISOString(),
            streaming_status: 'DONE',
            updated_at: new Date().toISOString(),
          };

          // Optimistically add user message to cache
          let latestMessages = [...currentData.messages, tempUserMessage];
          let latestDeltaAccumulator = currentData.deltaAccumulator;

          queryClient.setQueryData<TaskMessagesData>(queryKey, {
            messages: latestMessages,
            deltaAccumulator: latestDeltaAccumulator,
          });

          const controller = new AbortController();

          // Stream agent response and update cache in real-time
          for await (const response of agentRPCWithStreaming(
            agentexClient,
            { agentName },
            'message/send',
            { task_id: taskId, content },
            { signal: controller.signal }
          )) {
            if (response.error != null) {
              throw new Error(response.error.message);
            }

            // Get current state from cache (might have been updated by SSE subscription)
            const cacheData =
              queryClient.getQueryData<TaskMessagesData>(queryKey);
            if (cacheData) {
              latestMessages = cacheData.messages;
              latestDeltaAccumulator = cacheData.deltaAccumulator;
            }

            // Aggregate the message events
            const result = aggregateMessageEvents(
              latestMessages,
              latestDeltaAccumulator,
              [response.result]
            );

            latestMessages = result.messages;
            latestDeltaAccumulator = result.deltaAccumulator;

            // Update the cache immediately during streaming
            queryClient.setQueryData<TaskMessagesData>(queryKey, {
              messages: latestMessages,
              deltaAccumulator: latestDeltaAccumulator,
            });

            // If the last message is done, invalidate the spans query
            if (response.result.type === 'done') {
              queryClient.invalidateQueries({ queryKey: ['spans', taskId] });
            }
          }

          // Replace temporary user message with server-authoritative version
          const finalMessages = await agentexClient.messages.list({
            task_id: taskId,
          });

          queryClient.setQueryData<TaskMessagesData>(queryKey, {
            messages: finalMessages,
            deltaAccumulator: null,
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
