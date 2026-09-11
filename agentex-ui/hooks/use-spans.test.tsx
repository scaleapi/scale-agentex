import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useSpans } from './use-spans';

vi.mock('@/hooks/use-safe-search-params', () => ({
  useSafeSearchParams: () => ({ sgpAccountID: 'acct-1' }),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const span = {
  id: 'span-1',
  trace_id: 'task-1',
  parent_id: null,
  name: 'run_agent',
  start_timestamp: '2026-01-01T00:00:00Z',
  end_timestamp: null,
};

describe('useSpans', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads the task trace through the BFF with the selected account', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [span], has_more: false }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useSpans('task-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.spans).toEqual([span]);
    expect(result.current.hasMore).toBe(false);
    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe('/api/traces/task-1/spans');
    expect(init.credentials).toBe('include');
    expect(init.headers).toEqual({ 'x-selected-account-id': 'acct-1' });
  });

  it('reports when the trace has more spans than the page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ items: [span], has_more: true }))
    );

    const { result } = renderHook(() => useSpans('task-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.spans).toEqual([span]);
    expect(result.current.hasMore).toBe(true);
  });

  it('surfaces the BFF error message when the platform is not configured', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ error: 'SGP traces are not configured.' }, 503)
        )
    );

    const { result } = renderHook(() => useSpans('task-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() =>
      expect(result.current.error).toBe('SGP traces are not configured.')
    );
    expect(result.current.spans).toEqual([]);
  });

  it('does not fetch without a task', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useSpans(null), {
      wrapper: createWrapper(),
    });

    expect(result.current.spans).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
