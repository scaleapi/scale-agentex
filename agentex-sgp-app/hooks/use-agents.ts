import { useQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

/**
 * Query key factory for agents
 */
export const agentsKeys = {
  all: ['agents'] as const,
};

/**
 * Fetches the list of agents
 * This replaces useFetchAgents and can be renamed to that if needed
 */
export function useAgents(agentexClient: AgentexSDK) {
  return useQuery({
    queryKey: agentsKeys.all,
    queryFn: async (): Promise<Agent[]> => {
      return agentexClient.agents.list();
    },
    staleTime: 5 * 60 * 1000, // 5 minutes - agents don't change often
    refetchOnWindowFocus: false,
  });
}
