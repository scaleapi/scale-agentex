import { useQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type { Task } from 'agentex/resources';

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
 * Fetches the list of tasks, optionally filtered by agent name
 */
export function useTasks(
  agentexClient: AgentexSDK,
  options?: { agentName?: string }
) {
  const { agentName } = options || {};

  return useQuery({
    queryKey: tasksKeys.byAgentName(agentName),
    queryFn: async (): Promise<Task[]> => {
      const params = agentName ? { agent_name: agentName } : undefined;
      return agentexClient.tasks.list(params);
    },
    staleTime: 30 * 1000, // 30 seconds
    refetchOnWindowFocus: true,
  });
}

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
    queryFn: async (): Promise<Task> => {
      return agentexClient.tasks.retrieve(taskId);
    },
    enabled: !!taskId,
    staleTime: 30 * 1000,
  });
}
