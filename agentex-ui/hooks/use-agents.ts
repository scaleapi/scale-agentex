import { useQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

export const agentsKeys = {
  all: ['agents'] as const,
};

export function useAgents(agentexClient: AgentexSDK) {
  return useQuery({
    queryKey: agentsKeys.all,
    queryFn: async (): Promise<Agent[]> => {
      return agentexClient.agents.list();
    },
    refetchOnWindowFocus: false,
  });
}
