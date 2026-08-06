import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  AGENTS_PAGE_SIZE as PAGE_SIZE,
  MAX_AGENT_PAGES,
  useAgents,
} from './use-agents';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

function makeAgents(count: number, prefix: string): Agent[] {
  return Array.from(
    { length: count },
    (_, i) =>
      ({
        id: `${prefix}-${i}`,
        name: `${prefix}-${i}`,
        status: 'Ready',
      }) as Agent
  );
}

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

function clientWith(list: ReturnType<typeof vi.fn>) {
  return { agents: { list } } as unknown as AgentexSDK;
}

describe('useAgents', () => {
  it('pages through every agent until a short page is returned', async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(makeAgents(PAGE_SIZE, 'p1')) // full page -> keep going
      .mockResolvedValueOnce(makeAgents(24, 'p2')); // short page -> stop

    const { result } = renderHook(() => useAgents(clientWith(list)), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(PAGE_SIZE + 24);
    expect(list).toHaveBeenCalledTimes(2);
    expect(list).toHaveBeenNthCalledWith(1, {
      limit: PAGE_SIZE,
      page_number: 1,
    });
    expect(list).toHaveBeenNthCalledWith(2, {
      limit: PAGE_SIZE,
      page_number: 2,
    });
  });

  it('makes a single request when the first page is not full', async () => {
    const list = vi.fn().mockResolvedValueOnce(makeAgents(10, 'only'));

    const { result } = renderHook(() => useAgents(clientWith(list)), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(10);
    expect(list).toHaveBeenCalledTimes(1);
  });

  it('returns an empty list without paging when there are no agents', async () => {
    const list = vi.fn().mockResolvedValueOnce([]);

    const { result } = renderHook(() => useAgents(clientWith(list)), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
    expect(list).toHaveBeenCalledTimes(1);
  });

  it('stops at the exact-multiple boundary without looping forever', async () => {
    // Total is an exact multiple of the page size: a full page followed by an empty page.
    const list = vi
      .fn()
      .mockResolvedValueOnce(makeAgents(PAGE_SIZE, 'p1'))
      .mockResolvedValueOnce([]);

    const { result } = renderHook(() => useAgents(clientWith(list)), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(PAGE_SIZE);
    expect(list).toHaveBeenCalledTimes(2);
  });

  it('stops at the safety bound and warns when every page stays full', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    // Always return a full page so the loop can only stop at MAX_AGENT_PAGES.
    const list = vi.fn().mockResolvedValue(makeAgents(PAGE_SIZE, 'full'));

    const { result } = renderHook(() => useAgents(clientWith(list)), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(list).toHaveBeenCalledTimes(MAX_AGENT_PAGES);
    expect(result.current.data).toHaveLength(PAGE_SIZE * MAX_AGENT_PAGES);
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('MAX_AGENT_PAGES')
    );

    warn.mockRestore();
  });

  it('surfaces an error instead of a partial list when a page fails mid-loop', async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(makeAgents(PAGE_SIZE, 'p1'))
      .mockRejectedValueOnce(new Error('boom'));

    const { result } = renderHook(() => useAgents(clientWith(list)), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.data).toBeUndefined();
    expect(list).toHaveBeenCalledTimes(2);
  });
});
