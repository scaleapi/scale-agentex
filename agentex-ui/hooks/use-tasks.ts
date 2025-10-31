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
