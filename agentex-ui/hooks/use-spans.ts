'use client';

import { useQuery } from '@tanstack/react-query';

import { useAgentexClient } from '@/components/providers';

import type { Span } from 'agentex/resources';

export const spansKeys = {
  all: ['spans'] as const,
  byTaskId: (taskId: string | null) =>
    taskId ? ([...spansKeys.all, 'task', taskId] as const) : spansKeys.all,
};

type UseSpansState = {
  spans: Span[];
  isLoading: boolean;
  error: string | null;
};

/**
 * Fetches execution spans for observability and debugging of task execution.
 *
 * Queries by task_id first. Falls back to trace_id=taskId for backward
 * compatibility with spans created before the task_id column was added.
 *
 * @param taskId - string | null - The task ID to fetch spans for, or null to disable the query
 * @returns UseSpansState - Object containing the spans array, loading state, and any error message
 */
export function useSpans(taskId: string | null): UseSpansState {
  const { agentexClient } = useAgentexClient();

  const { data, isLoading, error } = useQuery<Span[], Error>({
    queryKey: spansKeys.byTaskId(taskId),
    queryFn: async ({ signal }) => {
      if (!taskId) {
        return [];
      }

      // Try querying by task_id first
      const spansByTaskId = await agentexClient.spans.list(
        { task_id: taskId } as Parameters<typeof agentexClient.spans.list>[0],
        { signal }
      );

      if (spansByTaskId.length > 0) {
        return spansByTaskId;
      }

      // Fallback: query by trace_id=taskId for backward compat with old spans
      return await agentexClient.spans.list({ trace_id: taskId }, { signal });
    },
    enabled: taskId !== null,
  });

  return {
    spans: data ?? [],
    isLoading,
    error: error?.message ?? null,
  };
}
