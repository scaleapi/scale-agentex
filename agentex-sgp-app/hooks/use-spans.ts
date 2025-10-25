'use client';

import { useQuery } from '@tanstack/react-query';

import { useAgentexClient } from '@/components/providers';

import type { Span } from 'agentex/resources';

type UseSpansState = {
  spans: Span[];
  isLoading: boolean;
  error: string | null;
};

export function useSpans(traceId: string | null): UseSpansState {
  const { agentexClient } = useAgentexClient();

  const { data, isLoading, error } = useQuery<Span[], Error>({
    queryKey: ['spans', traceId],
    queryFn: async ({ signal }) => {
      if (!traceId) {
        return [];
      }
      return await agentexClient.spans.list({ trace_id: traceId }, { signal });
    },
    enabled: traceId !== null,
  });

  return {
    spans: data ?? [],
    isLoading,
    error: error?.message ?? null,
  };
}
