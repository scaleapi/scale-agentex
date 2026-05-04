import { useMemo } from 'react';

import {
  InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import {
  agentRPCNonStreaming,
  agentRPCWithStreaming,
  aggregateMessageEvents,
} from 'agentex/lib';
import { v4 } from 'uuid';

import { toast } from '@/components/ui/toast';
import { fetchMessagesPage, MESSAGES_PAGE_SIZE } from '@/hooks/fetch-messages';
import { agentsKeys } from '@/hooks/use-agents';

import type AgentexSDK from 'agentex';
import type { IDeltaAccumulator } from 'agentex/lib';
import type { Agent, TaskMessage, TaskMessageContent } from 'agentex/resources';

export type TaskMessagesMetadata = {
  deltaAccumulator: IDeltaAccumulator | null;
  rpcStatus: 'idle' | 'pending' | 'success' | 'error';
};

export const taskMessagesKeys = {
  all: ['taskMessages'] as const,
  byTaskId: (taskId: string) => [...taskMessagesKeys.all, taskId] as const,
};

export const taskMessagesMetaKeys = {
  byTaskId: (taskId: string) => ['taskMessagesMeta', taskId] as const,
};

/**
 * Fetches conversation messages for a task using infinite scroll pagination.
 *
 * Page 1 = newest messages from the API. Scrolling up loads page 2, 3, etc (older).
 * Returns a flat, deduplicated, chronologically ordered messages array.
 */
export function useTaskMessages({
  agentexClient,
  taskId,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
}) {
  const queryClient = useQueryClient();

  const infiniteQuery = useInfiniteQuery({
    queryKey: taskMessagesKeys.byTaskId(taskId),
    queryFn: async ({ pageParam }): Promise<TaskMessage[]> => {
      if (!taskId) return [];
      return fetchMessagesPage(agentexClient, taskId, pageParam);
    },
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < MESSAGES_PAGE_SIZE) return undefined;
      return allPages.length + 1;
    },
    initialPageParam: 1,
    enabled: !!taskId,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  // Flatten pages into a single chronological array with deduplication.
  // Pages are stored as [page1(newest), page2(older), page3(oldest), ...]
  // Process newest-first so latest versions of messages win, then reverse.
  const messages = useMemo(() => {
    if (!infiniteQuery.data?.pages) return [];
    const seen = new Set<string>();
    const byPage: TaskMessage[][] = [];
    for (const page of infiniteQuery.data.pages) {
      const filtered: TaskMessage[] = [];
      for (const msg of page) {
        const id = msg.id ?? '';
        if (!id || !seen.has(id)) {
          if (id) seen.add(id);
          filtered.push(msg);
        }
      }
      byPage.push(filtered);
    }
    return byPage.reverse().flat();
  }, [infiniteQuery.data?.pages]);

  const metadata =
    queryClient.getQueryData<TaskMessagesMetadata>(
      taskMessagesMetaKeys.byTaskId(taskId)
    ) ?? ({ deltaAccumulator: null, rpcStatus: 'idle' } as const);

  return {
    messages,
    rpcStatus: metadata.rpcStatus,
    fetchNextPage: infiniteQuery.fetchNextPage,
    hasNextPage: infiniteQuery.hasNextPage,
    isFetchingNextPage: infiniteQuery.isFetchingNextPage,
    isLoading: infiniteQuery.isLoading,
  };
}

type SendMessageParams = {
  taskId: string;
  agentName: string;
  content: TaskMessageContent;
};

/** Helper to update just the first page (newest) of the infinite query cache. */
function updateFirstPage(
  oldData: InfiniteData<TaskMessage[]> | undefined,
  updater: (firstPage: TaskMessage[]) => TaskMessage[]
): InfiniteData<TaskMessage[]> {
  if (!oldData) {
    return { pages: [updater([])], pageParams: [1] };
  }
  return {
    pages: [updater(oldData.pages[0] ?? []), ...oldData.pages.slice(1)],
    pageParams: oldData.pageParams,
  };
}

export function useSendMessage({
  agentexClient,
}: {
  agentexClient: AgentexSDK;
}) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ taskId, agentName, content }: SendMessageParams) => {
      const queryKey = taskMessagesKeys.byTaskId(taskId);
      const metaKey = taskMessagesMetaKeys.byTaskId(taskId);

      const agents = queryClient.getQueryData<Agent[]>(agentsKeys.all) || [];
      const agent = agents.find(a => a.name === agentName);

      if (!agent) {
        throw new Error(`Agent with name ${agentName} not found`);
      }

      switch (agent.acp_type) {
        case 'async':
        case 'agentic': {
          queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
            deltaAccumulator: null,
            rpcStatus: 'pending',
          });

          const response = await agentRPCNonStreaming(
            agentexClient,
            { agentName },
            'event/send',
            { task_id: taskId, content }
          );

          if (response.error != null) {
            queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
              deltaAccumulator: null,
              rpcStatus: 'error',
            });
            throw new Error(response.error.message);
          }

          // Refetch spans now that the agent has finished processing
          queryClient.invalidateQueries({ queryKey: ['spans', taskId] });

          // Refetch all loaded pages so the cache stays consistent when the
          // user has scrolled up and loaded older pages — refetching only
          // page 1 leaves a stale gap at the page boundary as the thread grows.
          // Use refetchQueries (not invalidateQueries) so the fetch runs even
          // when there are no active observers (e.g. component unmounted mid-RPC).
          await queryClient.refetchQueries({ queryKey });

          queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
            deltaAccumulator: null,
            rpcStatus: 'success',
          });

          const latestData =
            queryClient.getQueryData<InfiniteData<TaskMessage[]>>(queryKey);
          return { messages: latestData?.pages[0] ?? [] };
        }

        case 'sync': {
          // Read current flattened messages from cache for streaming
          const existingData =
            queryClient.getQueryData<InfiniteData<TaskMessage[]>>(queryKey);
          const existingMeta =
            queryClient.getQueryData<TaskMessagesMetadata>(metaKey);

          const flatMessages = existingData
            ? [...existingData.pages].reverse().flat()
            : [];

          const tempUserMessage: TaskMessage = {
            id: v4(),
            content,
            task_id: taskId,
            created_at: new Date().toISOString(),
            streaming_status: 'DONE',
            updated_at: new Date().toISOString(),
          };

          let latestMessages = [...flatMessages, tempUserMessage];
          let latestDeltaAccumulator = existingMeta?.deltaAccumulator ?? null;

          // Optimistic: add user message to first page
          queryClient.setQueryData<InfiniteData<TaskMessage[]>>(queryKey, old =>
            updateFirstPage(old, firstPage => [...firstPage, tempUserMessage])
          );
          queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
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
              queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
                deltaAccumulator: null,
                rpcStatus: 'error',
              });
              throw new Error(response.error.message);
            }

            const result = aggregateMessageEvents(
              latestMessages,
              latestDeltaAccumulator,
              [response.result]
            );

            latestMessages = result.messages;
            latestDeltaAccumulator = result.deltaAccumulator;

            // Write streaming state to first page
            queryClient.setQueryData<InfiniteData<TaskMessage[]>>(
              queryKey,
              old => updateFirstPage(old, () => latestMessages)
            );
            queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
              deltaAccumulator: latestDeltaAccumulator,
              rpcStatus: 'pending',
            });

            if (response.result.type === 'done') {
              queryClient.invalidateQueries({ queryKey: ['spans', taskId] });
            }
          }

          // Final reconciliation: refetch all loaded pages so the cache stays
          // consistent when older pages have been loaded — refetching only
          // page 1 leaves a stale gap at the page boundary as the thread grows.
          // Use refetchQueries (not invalidateQueries) so the fetch runs even
          // when there are no active observers (e.g. component unmounted mid-stream).
          await queryClient.refetchQueries({ queryKey });

          queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
            deltaAccumulator: null,
            rpcStatus: 'success',
          });

          const latestData =
            queryClient.getQueryData<InfiniteData<TaskMessage[]>>(queryKey);
          return { messages: latestData?.pages[0] ?? [] };
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
