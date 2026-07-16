import { useCallback, useMemo, useRef } from 'react';

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

  // Keeps the sync `message/send` stream AbortController reachable so a Stop
  // action can abort the in-flight streaming connection. Async agents have no
  // local stream to abort; abortStream is a no-op for them.
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());

  const abortStream = useCallback((taskId: string) => {
    const controller = abortControllersRef.current.get(taskId);
    if (controller) {
      controller.abort();
      abortControllersRef.current.delete(taskId);
    }
  }, []);

  const mutation = useMutation({
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
          abortControllersRef.current.set(taskId, controller);

          try {
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
          } catch (streamError) {
            // A user Stop aborts the controller; that is an expected end of the
            // stream, not a failure. Any other error propagates to onError.
            if (!controller.signal.aborted) {
              throw streamError;
            }
          } finally {
            abortControllersRef.current.delete(taskId);
          }

          // Final reconciliation: refetch all loaded pages so the cache stays
          // consistent when older pages have been loaded — refetching only
          // page 1 leaves a stale gap at the page boundary as the thread grows.
          // Use refetchQueries (not invalidateQueries) so the fetch runs even
          // when there are no active observers (e.g. component unmounted mid-stream).
          await queryClient.refetchQueries({ queryKey });

          // On a Stop the shimmer must clear immediately (idle); a normal
          // completion settles to success.
          queryClient.setQueryData<TaskMessagesMetadata>(metaKey, {
            deltaAccumulator: null,
            rpcStatus: controller.signal.aborted ? 'idle' : 'success',
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

  return Object.assign(mutation, { abortStream });
}

type InterruptTurnParams = {
  taskId: string;
  agentName: string;
  reason?: string | null;
};

/**
 * Thin adapter for the assumed `task/interrupt` shape. The typed SDK method is
 * not generated yet, so this hits the REST route directly.
 *
 * TODO(AGX1-391): swap to the typed SDK method once the OpenAPI `task/interrupt`
 * change lands, e.g. `agentexClient.tasks.interrupt(taskId, { reason })`, or the
 * RPC form `agentRPCNonStreaming(agentexClient, { agentName }, 'task/interrupt',
 * { task_id: taskId })`.
 */
async function interruptTaskAdapter(
  agentexClient: AgentexSDK,
  { taskId, reason }: InterruptTurnParams
): Promise<void> {
  await agentexClient.post(`/tasks/${taskId}/interrupt`, {
    body: { reason: reason ?? null },
  });
}

/**
 * Interrupts the current turn without terminating the task. Forces the message
 * meta cache to idle on settle so the thinking indicator clears. Does NOT abort
 * the SSE task subscription — that stays live so later turns keep streaming.
 */
export function useInterruptTurn({
  agentexClient,
}: {
  agentexClient: AgentexSDK;
}) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: InterruptTurnParams) => {
      return interruptTaskAdapter(agentexClient, params);
    },
    onSettled: (_data, _error, variables) => {
      queryClient.setQueryData<TaskMessagesMetadata>(
        taskMessagesMetaKeys.byTaskId(variables.taskId),
        { deltaAccumulator: null, rpcStatus: 'idle' }
      );
    },
    onError: error => {
      toast.error({
        title: 'Failed to stop the current turn',
        message: error instanceof Error ? error.message : 'Please try again.',
      });
    },
  });
}
