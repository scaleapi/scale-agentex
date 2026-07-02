import { useQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

export const agentByNameKeys = {
  byName: (name: string) => ['agents', 'by-name', name] as const,
};

/**
 * Fetches a single agent by its unique name.
 *
 * Used to validate a deep-linked `agent_name` directly against the backend so that opening
 * an agent does not depend on the entire (paginated) agent list having been loaded first.
 * The query is disabled when no name is provided, and a missing/unknown agent resolves to
 * `null` rather than throwing so callers can treat "not found" as a normal outcome.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to communicate with the Agentex API
 * @param agentName - The agent name to look up; query is disabled when absent (null/undefined)
 * @returns UseQueryResult<Agent | null> - React Query result containing the agent, or null if not found
 */
export function useAgentByName(
  agentexClient: AgentexSDK,
  agentName: string | null | undefined
) {
  return useQuery({
    queryKey: agentByNameKeys.byName(agentName ?? ''),
    queryFn: async (): Promise<Agent | null> => {
      try {
        return await agentexClient.agents.retrieveByName(agentName as string);
      } catch {
        // A 404 (or any lookup failure) means the name isn't a valid, reachable agent.
        return null;
      }
    },
    enabled: !!agentName,
    refetchOnWindowFocus: false,
  });
}
