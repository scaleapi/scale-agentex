import { useQuery } from '@tanstack/react-query';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

export const agentsKeys = {
  all: ['agents'] as const,
};

/**
 * Page size used when paging through the full agent list.
 *
 * The `/agents` endpoint is offset-paginated (1-indexed `page_number`) and defaults to
 * 50 agents per page, so a single unpaginated call only ever returns the first page. We
 * request a larger page and keep fetching until a page comes back short.
 */
export const AGENTS_PAGE_SIZE = 100;

/**
 * Upper bound on the number of pages we fetch, as a safety valve against an unbounded
 * loop if the backend ever stops short-paging. At {@link AGENTS_PAGE_SIZE} per page this
 * covers far more agents than any real account.
 */
export const MAX_AGENT_PAGES = 100;

/**
 * Fetches the complete list of agents available in the system.
 *
 * The list endpoint is paginated, so this pages through every result — accumulating until
 * a page returns fewer than {@link AGENTS_PAGE_SIZE} items — rather than returning only the
 * default first page. Refetch on window focus is disabled to prevent unnecessary API calls
 * when switching browser tabs.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to communicate with the Agentex API
 * @returns UseQueryResult<Agent[]> - React Query result containing the array of agent definitions
 */
export function useAgents(agentexClient: AgentexSDK) {
  return useQuery({
    queryKey: agentsKeys.all,
    queryFn: async (): Promise<Agent[]> => {
      const allAgents: Agent[] = [];

      for (let pageNumber = 1; pageNumber <= MAX_AGENT_PAGES; pageNumber++) {
        const page = await agentexClient.agents.list({
          limit: AGENTS_PAGE_SIZE,
          page_number: pageNumber,
        });

        allAgents.push(...page);

        // A short page means we've reached the end of the list.
        if (page.length < AGENTS_PAGE_SIZE) break;

        // Still a full page on the last allowed iteration: we've hit the safety bound
        // with more agents likely remaining. Warn loudly rather than silently truncating
        // (a silent truncation would reintroduce the "missing agents" bug this fix closes).
        if (pageNumber === MAX_AGENT_PAGES) {
          console.warn(
            `useAgents: reached MAX_AGENT_PAGES (${MAX_AGENT_PAGES}) with a full final page; ` +
              `the agent list may be truncated at ${allAgents.length} agents.`
          );
        }
      }

      return allAgents;
    },
    refetchOnWindowFocus: false,
  });
}
