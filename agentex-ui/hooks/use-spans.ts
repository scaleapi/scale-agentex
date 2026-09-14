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
  window_truncated?: boolean;
  effective_from_ts?: string | null;
};

type SpansResult = {
  items: TraceSpan[];
  hasMore: boolean;
  truncatedBefore: string | null;
};

type UseSpansOptions = {
  // False while the sidebar is collapsed, so a hidden panel does not search the platform.
  enabled?: boolean;
};

type UseSpansState = {
  spans: TraceSpan[];
  // True when the trace has more spans than the one page the sidebar shows.
  hasMore: boolean;
  // Set when the platform clamped the window, to the earliest instant it did search.
  truncatedBefore: string | null;
  isLoading: boolean;
  error: string | null;
};

/**
 * Fetches a task's execution spans from Scale GenAI Platform, where agents trace under the
 * task id, through the same-origin BFF route that attaches credentials server-side.
 *
 * @param taskId - The task ID to fetch spans for, or null to disable the query
 * @param createdAt - The task's creation time, which starts the platform's search window.
 *   Undefined means not known yet (the query waits), null means unknown (no window is sent).
 * @param options - `enabled: false` holds the query while the sidebar is collapsed.
 * @returns The first page of spans in start order, whether more exist, where the platform
 *   truncated the window, the loading state, and any error message
 */
export function useSpans(
  taskId: string | null,
  createdAt: string | null | undefined,
  { enabled = true }: UseSpansOptions = {}
): UseSpansState {
  const { sgpAccountID } = useSafeSearchParams();
  const { authEnabled } = useAgentexClient();

  const { data, isPending, error } = useQuery<SpansResult, Error>({
    queryKey: spansKeys.byTaskId(taskId, sgpAccountID, createdAt),
    queryFn: async ({ signal }): Promise<SpansResult> => {
      if (!taskId) {
        return { items: [], hasMore: false, truncatedBefore: null };
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
      return {
        items: page.items ?? [],
        hasMore: page.has_more ?? false,
        truncatedBefore:
          page.window_truncated && page.effective_from_ts
            ? page.effective_from_ts
            : null,
      };
    },
    enabled: enabled && taskId !== null && createdAt !== undefined,
  });

  return {
    spans: data?.items ?? [],
    hasMore: data?.hasMore ?? false,
    truncatedBefore: data?.truncatedBefore ?? null,
    // No data yet, whether the query is waiting on the task or in flight, reads as loading.
    isLoading: isPending,
    error: error?.message ?? null,
  };
}
