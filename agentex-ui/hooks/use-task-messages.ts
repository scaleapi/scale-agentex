import {
  InfiniteData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import {
  agentRPCNonStreaming,
  agentRPCWithStreaming,
  aggregateMessageEvents,
} from 'agentex/lib';
import { v4 } from 'uuid';

import { toast } from '@/components/ui/toast';
import { agentsKeys } from '@/hooks/use-agents';
import {
  infiniteTaskMessagesKeys,
  PaginatedMessagesResponse,
} from '@/hooks/use-infinite-task-messages';

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

      // Uses default limit (50) - for full history use useInfiniteTaskMessages
      const response = await agentexClient.messages.list({
        task_id: taskId,
      });

      // API returns messages in descending order (newest first),
      // reverse to chronological order (oldest first) for display
      return {
        messages: response.data.slice().reverse(),
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
      const agents = queryClient.getQueryData<Agent[]>(agentsKeys.all) || [];
      const agent = agents.find(a => a.name === agentName);

      if (!agent) {
        throw new Error(`Agent with name ${agentName} not found`);
      }

      switch (agent.acp_type) {
        case 'async':
        case 'agentic': {
          const infiniteQueryKey = infiniteTaskMessagesKeys.byTaskId(taskId);

          // Cancel any in-flight queries to prevent race conditions
          await queryClient.cancelQueries({ queryKey: infiniteQueryKey });

          // Add optimistic update to show user's message immediately
          const tempUserMessage: TaskMessage = {
            id: v4(),
            content,
            task_id: taskId,
            created_at: new Date().toISOString(),
            streaming_status: 'DONE',
            updated_at: new Date().toISOString(),
          };

          // Get current messages and add the user's message optimistically
          const currentInfiniteData =
            queryClient.getQueryData<
              InfiniteData<PaginatedMessagesResponse, string | undefined>
            >(infiniteQueryKey);

          const currentMessages = currentInfiniteData
            ? currentInfiniteData.pages.flatMap(page => page.data).reverse()
            : [];
          const updatedMessages = [...currentMessages, tempUserMessage];
          const newestFirst = [...updatedMessages].reverse();

          queryClient.setQueryData<
            InfiniteData<PaginatedMessagesResponse, string | undefined>
          >(infiniteQueryKey, oldData => ({
            pages: [
              {
                data: newestFirst,
                next_cursor: oldData?.pages[0]?.next_cursor ?? null,
                has_more: oldData?.pages[0]?.has_more ?? false,
              },
              ...(oldData?.pages.slice(1) ?? []),
            ],
            pageParams: oldData?.pageParams ?? [undefined],
          }));

          // Send the event to the backend
          const response = await agentRPCNonStreaming(
            agentexClient,
            { agentName },
            'event/send',
            { task_id: taskId, content }
          );

          if (response.error != null) {
            throw new Error(response.error.message);
          }

          // Invalidate and refetch after a short delay to ensure we get the latest state
          // This is a fallback in case the subscription doesn't update correctly
          setTimeout(() => {
            queryClient.invalidateQueries({
              queryKey: infiniteTaskMessagesKeys.byTaskId(taskId),
            });
          }, 500);

          return {
            messages: updatedMessages,
            deltaAccumulator: null,
            rpcStatus: 'pending',
          };
        }

        case 'sync': {
          const infiniteQueryKey = infiniteTaskMessagesKeys.byTaskId(taskId);

          // Cancel any in-flight queries to prevent race conditions
          await queryClient.cancelQueries({ queryKey: infiniteQueryKey });

          // Get current messages from infinite query cache
          const currentInfiniteData =
            queryClient.getQueryData<
              InfiniteData<PaginatedMessagesResponse, string | undefined>
            >(infiniteQueryKey);

          // Extract current messages (flattened and in chronological order)
          let latestMessages: TaskMessage[] = currentInfiniteData
            ? currentInfiniteData.pages.flatMap(page => page.data).reverse()
            : [];
          let latestDeltaAccumulator: IDeltaAccumulator | null = null;

          const tempUserMessage: TaskMessage = {
            id: v4(),
            content,
            task_id: taskId,
            created_at: new Date().toISOString(),
            streaming_status: 'DONE',
            updated_at: new Date().toISOString(),
          };

          latestMessages = [...latestMessages, tempUserMessage];

          // Update the infinite query with optimistic update
          const updateInfiniteCache = (messages: TaskMessage[]) => {
            // Convert to newest-first for API format
            const newestFirst = [...messages].reverse();
            queryClient.setQueryData<
              InfiniteData<PaginatedMessagesResponse, string | undefined>
            >(infiniteQueryKey, oldData => ({
              pages: [
                {
                  data: newestFirst,
                  next_cursor: oldData?.pages[0]?.next_cursor ?? null,
                  has_more: oldData?.pages[0]?.has_more ?? false,
                },
                ...(oldData?.pages.slice(1) ?? []),
              ],
              pageParams: oldData?.pageParams ?? [undefined],
            }));
          };

          updateInfiniteCache(latestMessages);

          const controller = new AbortController();

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

            const result = aggregateMessageEvents(
              latestMessages,
              latestDeltaAccumulator,
              [response.result]
            );

            latestMessages = result.messages;
            latestDeltaAccumulator = result.deltaAccumulator;

            updateInfiniteCache(latestMessages);

            if (response.result.type === 'done') {
              queryClient.invalidateQueries({ queryKey: ['spans', taskId] });
            }
          }

          // Fetch final state from server to ensure consistency
          const response = await agentexClient.messages.list({
            task_id: taskId,
          });

          // API returns messages in descending order (newest first)
          const newestFirstMessages = response.data;
          const chronologicalMessages = newestFirstMessages.slice().reverse();

          // Update the first page with server data
          queryClient.setQueryData<
            InfiniteData<PaginatedMessagesResponse, string | undefined>
          >(infiniteQueryKey, oldData => ({
            pages: [
              {
                data: newestFirstMessages,
                next_cursor: response.next_cursor,
                has_more: response.has_more,
              },
              ...(oldData?.pages.slice(1) ?? []),
            ],
            pageParams: oldData?.pageParams ?? [undefined],
          }));

          return {
            messages: chronologicalMessages,
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
