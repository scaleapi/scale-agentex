import { useQuery } from '@tanstack/react-query';

import type { Agent } from 'agentex/resources';

export const agentsKeys = {
  all: ['agents'] as const,
};

/**
 * Fetches the complete list of agents available in the system.
 *
 * This hook retrieves all agent definitions that can execute tasks. Refetch on window focus
 * is disabled to prevent unnecessary API calls when switching browser tabs.
 *
 * @param agentexClient - any - The SDK client used to communicate with the Agentex API
 * @returns UseQueryResult<Agent[]> - React Query result containing the array of agent definitions
 */
export function useAgents(agentexClient: any) {
  return useQuery({
    queryKey: agentsKeys.all,
    queryFn: async (): Promise<Agent[]> => {
      return agentexClient.agents.list();
    },
    refetchOnWindowFocus: false,
  });
}
