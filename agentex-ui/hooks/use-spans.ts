'use client';

import { useQuery } from '@tanstack/react-query';

import { useAgentexClient } from '@/components/providers';

import type { Span } from 'agentex/resources';

export const spansKeys = {
  all: ['spans'] as const,
  byTraceId: (traceId: string | null) =>
    traceId ? ([...spansKeys.all, traceId] as const) : spansKeys.all,
};

type UseSpansState = {
  spans: Span[];
  isLoading: boolean;
  error: string | null;
};

/**
 * Fetches execution spans for observability and debugging of task execution.
 *
 * Spans are OpenTelemetry-style trace records that show the execution flow of an agent task.
 * The query is automatically disabled when no traceId is provided.
 *
 * @param traceId - string | null - The trace ID to fetch spans for, or null to disable the query
 * @returns UseSpansState - Object containing the spans array, loading state, and any error message
 */
export function useSpans(traceId: string | null): UseSpansState {
  const { agentexClient } = useAgentexClient();

  const { data, isLoading, error } = useQuery<Span[], Error>({
    queryKey: spansKeys.byTraceId(traceId),
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
