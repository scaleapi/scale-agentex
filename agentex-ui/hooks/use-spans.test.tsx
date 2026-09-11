import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { spansKeys, useSpans } from './use-spans';

vi.mock('@/hooks/use-safe-search-params', () => ({
  useSafeSearchParams: () => ({ sgpAccountID: 'acct-1' }),
}));

const providers = vi.hoisted(() => ({
  authEnabled: false,
  refreshSession: vi.fn(async () => undefined),
}));

vi.mock('@/components/providers', () => ({
  useAgentexClient: () => ({ authEnabled: providers.authEnabled }),
  refreshSession: providers.refreshSession,
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

describe('spansKeys', () => {
  it('scopes a task query to the selected account', () => {
    expect(spansKeys.byTaskId('task-1', 'acct-1', null)).not.toEqual(
      spansKeys.byTaskId('task-1', 'acct-2', null)
    );
  });
});

describe('useSpans', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    providers.authEnabled = false;
    providers.refreshSession.mockClear();
  });

  it('refreshes the session once and retries a 401 when login is enabled', async () => {
    providers.authEnabled = true;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(jsonResponse({ items: [span], has_more: false }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useSpans('task-1', null), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.spans).toEqual([span]);
    expect(providers.refreshSession).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not refresh on a 401 when login is disabled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'expired' }, 401))
    );

    const { result } = renderHook(() => useSpans('task-1', null), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('expired'));
    expect(providers.refreshSession).not.toHaveBeenCalled();
  });

  it('reads the task trace through the BFF with the selected account', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [span], has_more: false }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(
      () => useSpans('task-1', '2026-01-01T00:00:00.000Z'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.spans).toEqual([span]);
    expect(result.current.hasMore).toBe(false);
    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(
      '/api/traces/task-1/spans?from=2026-01-01T00%3A00%3A00.000Z'
    );
    expect(init.credentials).toBe('include');
    expect(init.headers).toEqual({ 'x-selected-account-id': 'acct-1' });
  });

  it('reports when the trace has more spans than the page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ items: [span], has_more: true }))
    );

    const { result } = renderHook(() => useSpans('task-1', null), {
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

    const { result } = renderHook(() => useSpans('task-1', null), {
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

    const { result } = renderHook(() => useSpans(null, null), {
      wrapper: createWrapper(),
    });

    expect(result.current.spans).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('waits until the task creation time is known', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    renderHook(() => useSpans('task-1', undefined), {
      wrapper: createWrapper(),
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reads without a window when the task cannot be loaded', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], has_more: false }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useSpans('task-1', null), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchMock.mock.calls[0]![0]).toBe('/api/traces/task-1/spans');
  });
});
