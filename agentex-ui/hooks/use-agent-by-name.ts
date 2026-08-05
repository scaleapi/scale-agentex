import { useQuery } from '@tanstack/react-query';
import { APIError } from 'agentex';

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
 * The query is disabled when no name is provided. A 404 resolves to `null` ("no such agent"
 * — a normal outcome), while any other failure (network / 5xx / auth) is re-thrown so React
 * Query surfaces it as an error rather than masquerading as "not found" (which could
 * otherwise clear a valid deep link).
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
      } catch (error) {
        // A 404 means the name isn't a real, reachable agent — a normal "not found"
        // outcome, so resolve to null. Re-throw anything else (network / 5xx / auth) so a
        // transient failure surfaces as a query error instead of masquerading as
        // "not found", which could otherwise clear a valid deep link.
        if (error instanceof APIError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
    enabled: !!agentName,
    refetchOnWindowFocus: false,
  });
}
