import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type {
  TaskListResponse,
  TaskListParams,
  TaskRetrieveResponse,
} from 'agentex/resources';

/**
 * Query key factory for tasks
 */
export const tasksKeys = {
  all: ['tasks'] as const,
  byAgentName: (agentName: string | undefined) =>
    agentName
      ? ([...tasksKeys.all, 'agent', agentName] as const)
      : tasksKeys.all,
  byId: (taskId: string) => [...tasksKeys.all, taskId] as const,
};

/**
 * Fetches a single task by ID
 */
export function useTask({
  agentexClient,
  taskId,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
}) {
  return useQuery({
    queryKey: tasksKeys.byId(taskId),
    queryFn: async (): Promise<TaskRetrieveResponse> => {
      return agentexClient.tasks.retrieve(taskId, {
        relationships: ['agents'],
      });
    },
    enabled: !!taskId,
    staleTime: 30 * 1000,
  });
}

/**
 * useQuery hook for infinite scrolling tasks
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
    staleTime: 30 * 1000,
    refetchOnWindowFocus: true,
  });
}
