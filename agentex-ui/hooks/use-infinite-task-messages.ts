import { useInfiniteQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type { PaginatedMessagesResponse, TaskMessage } from 'agentex/resources';

// Re-export for use in other hooks
export type { PaginatedMessagesResponse };

export const infiniteTaskMessagesKeys = {
  all: ['infiniteTaskMessages'] as const,
  byTaskId: (taskId: string) =>
    [...infiniteTaskMessagesKeys.all, taskId] as const,
};

export type InfiniteTaskMessagesData = {
  messages: TaskMessage[];
  hasMore: boolean;
};

/**
 * Fetches task messages with infinite scroll pagination.
 *
 * Uses cursor-based pagination to efficiently load older messages
 * as the user scrolls up. Messages are returned in chronological order
 * (oldest first) for display.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to fetch messages
 * @param taskId - string - The unique ID of the task whose messages to retrieve
 * @param limit - number - Number of messages to fetch per page (default: 50)
 * @returns UseInfiniteQueryResult with messages and pagination controls
 *
 * @example
 * const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
 *   useInfiniteTaskMessages({ agentexClient, taskId });
 *
 * // Load more older messages when user scrolls to top
 * if (hasNextPage && !isFetchingNextPage) {
 *   fetchNextPage();
 * }
 */
export function useInfiniteTaskMessages({
  agentexClient,
  taskId,
  limit = 50,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
  limit?: number;
}) {
  return useInfiniteQuery({
    queryKey: infiniteTaskMessagesKeys.byTaskId(taskId),
    queryFn: async ({ pageParam }): Promise<PaginatedMessagesResponse> => {
      return agentexClient.messages.listPaginated({
        task_id: taskId,
        limit,
        direction: 'older',
        ...(pageParam && { cursor: pageParam }),
      });
    },
    getNextPageParam: lastPage => {
      // Return next_cursor if there are more messages
      return lastPage.has_more ? lastPage.next_cursor : undefined;
    },
    initialPageParam: undefined as string | undefined,
    enabled: !!taskId,
    // Transform pages into a flat, chronologically ordered array
    select: data => {
      // Flatten all pages and reverse to get chronological order
      const allMessages = data.pages.flatMap(page => page.data);
      // Messages come newest first, so reverse for chronological order
      const chronologicalMessages = allMessages.slice().reverse();

      return {
        pages: data.pages,
        pageParams: data.pageParams,
        messages: chronologicalMessages,
        hasMore: data.pages[data.pages.length - 1]?.has_more ?? false,
      };
    },
  });
}
