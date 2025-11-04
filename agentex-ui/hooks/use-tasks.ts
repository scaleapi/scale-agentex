import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type {
  TaskListResponse,
  TaskListParams,
  TaskRetrieveResponse,
} from 'agentex/resources';

export const tasksKeys = {
  all: ['tasks'] as const,
  individual: ['task'] as const,
  byAgentName: (agentName: string | undefined) =>
    agentName ? ([...tasksKeys.all, agentName] as const) : tasksKeys.all,
  individualById: (taskId: string) =>
    [...tasksKeys.individual, taskId] as const,
};

/**
 * Fetches a single task with full details and relationships.
 *
 * Retrieves complete task information including status, parameters, and associated
 * agent relationships. The query is disabled when no taskId is provided to prevent
 * unnecessary API calls.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to fetch the task
 * @param taskId - string - The unique ID of the task to retrieve
 * @returns UseQueryResult<TaskRetrieveResponse> - Query result containing the full task details
 */
export function useTask({
  agentexClient,
  taskId,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
}) {
  return useQuery({
    queryKey: tasksKeys.individualById(taskId),
    queryFn: async (): Promise<TaskRetrieveResponse> => {
      return agentexClient.tasks.retrieve(taskId, {
        relationships: ['agents'],
      });
    },
    enabled: !!taskId,
  });
}

/**
 * Fetches tasks with infinite scroll pagination for task lists.
 *
 * Loads tasks in pages for efficient rendering of long task lists. Supports optional
 * filtering by agent name to show only tasks for a specific agent. Each task includes
 * agent relationships for display purposes.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to fetch paginated tasks
 * @param options - { agentName?: string; limit?: number } - Optional filters and page size configuration
 * @returns UseInfiniteQueryResult<InfiniteData<TaskListResponse>> - Infinite query with fetchNextPage support
 */
export function useInfiniteTasks(
  agentexClient: AgentexSDK,
  options?: { agentName?: string; limit?: number }
) {
  const { agentName, limit = 30 } = options || {};

  return useInfiniteQuery({
    queryKey: tasksKeys.byAgentName(agentName),
    queryFn: async ({ pageParam = 1 }): Promise<TaskListResponse> => {
      const params: TaskListParams = {
        limit,
        page_number: pageParam as number,
        relationships: ['agents'],
        ...(agentName ? { agent_name: agentName } : {}),
      };
      return agentexClient.tasks.list(params);
    },
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < limit) {
        return undefined;
      }
      return allPages.length + 1;
    },
    initialPageParam: 1,
  });
}
