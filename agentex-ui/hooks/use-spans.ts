'use client';

import { useQuery } from '@tanstack/react-query';

import { refreshSession, useAgentexClient } from '@/components/providers';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';

export const spansKeys = {
  all: ['spans'] as const,
  // The account and the window anchor scope the platform read, so they scope the cache too.
  byTaskId: (
    taskId: string | null,
    accountId: string | null,
    createdAt: string | null | undefined
  ) =>
    taskId
      ? ([
          ...spansKeys.all,
          'task',
          taskId,
          accountId ?? '',
          createdAt ?? '',
        ] as const)
      : spansKeys.all,
};

/** A platform span as the traces BFF route returns it. */
export type TraceSpan = {
  id: string;
  trace_id: string;
  parent_id: string | null;
  name: string;
  start_timestamp: string;
  end_timestamp: string | null;
  status?: string | null;
  type?: string | null;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
};

type SpansPage = {
  items: TraceSpan[];
  has_more?: boolean;
};

type SpansResult = {
  items: TraceSpan[];
  hasMore: boolean;
};

type UseSpansState = {
  spans: TraceSpan[];
  // True when the trace has more spans than the one page the sidebar shows.
  hasMore: boolean;
  isLoading: boolean;
  error: string | null;
};

/**
 * Fetches a task's execution spans from Scale GenAI Platform, where agents trace under the
 * task id, through the same-origin BFF route that attaches credentials server-side.
 *
 * @param taskId - The task ID to fetch spans for, or null to disable the query
 * @param createdAt - The task's creation time, which anchors the platform's search window.
 *   Undefined means not known yet (the query waits), null means unknown (no window is sent).
 * @returns The first page of spans in start order, whether more exist, the loading state, and any error message
 */
export function useSpans(
  taskId: string | null,
  createdAt: string | null | undefined
): UseSpansState {
  const { sgpAccountID } = useSafeSearchParams();
  const { authEnabled } = useAgentexClient();

  const { data, isLoading, error } = useQuery<SpansResult, Error>({
    queryKey: spansKeys.byTaskId(taskId, sgpAccountID, createdAt),
    queryFn: async ({ signal }): Promise<SpansResult> => {
      if (!taskId) {
        return { items: [], hasMore: false };
      }

      const search = createdAt
        ? `?${new URLSearchParams({ from: createdAt })}`
        : '';
      const url = `/api/traces/${encodeURIComponent(taskId)}/spans${search}`;
      const init: RequestInit = {
        credentials: 'include',
        // Selected account, same source as the SDK, forwarded by the BFF.
        headers: sgpAccountID ? { 'x-selected-account-id': sgpAccountID } : {},
        signal,
      };
      let response = await fetch(url, init);
      if (response.status === 401 && authEnabled) {
        // The access token expired between refreshes, so refresh once and retry like the SDK client.
        await refreshSession();
        response = await fetch(url, init);
      }

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const message =
          typeof body.error === 'string'
            ? body.error
            : typeof body.detail === 'string'
              ? body.detail
              : `Request failed with status ${response.status}`;
        throw new Error(message);
      }

      const page: SpansPage = await response.json();
      return { items: page.items ?? [], hasMore: page.has_more ?? false };
    },
    enabled: taskId !== null && createdAt !== undefined,
  });

  return {
    spans: data?.items ?? [],
    hasMore: data?.hasMore ?? false,
    isLoading,
    error: error?.message ?? null,
  };
}
