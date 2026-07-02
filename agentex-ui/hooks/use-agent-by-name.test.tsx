import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useAgentByName } from './use-agent-by-name';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

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

function clientWith(retrieveByName: ReturnType<typeof vi.fn>) {
  return { agents: { retrieveByName } } as unknown as AgentexSDK;
}

describe('useAgentByName', () => {
  it('does not fetch when no agent name is provided', () => {
    const retrieveByName = vi.fn();

    const { result } = renderHook(
      () => useAgentByName(clientWith(retrieveByName), null),
      {
        wrapper: createWrapper(),
      }
    );

    expect(retrieveByName).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
    expect(result.current.data).toBeUndefined();
  });

  it('returns the agent when the lookup succeeds', async () => {
    const agent = {
      id: 'a1',
      name: 'interview-agent',
      status: 'Ready',
    } as Agent;
    const retrieveByName = vi.fn().mockResolvedValueOnce(agent);

    const { result } = renderHook(
      () => useAgentByName(clientWith(retrieveByName), 'interview-agent'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(agent);
    expect(retrieveByName).toHaveBeenCalledWith('interview-agent');
  });

  it('resolves to null (not an error) when the lookup fails', async () => {
    const retrieveByName = vi
      .fn()
      .mockRejectedValueOnce(new Error('404 not found'));

    const { result } = renderHook(
      () => useAgentByName(clientWith(retrieveByName), 'missing-agent'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toBeNull();
    expect(result.current.isError).toBe(false);
  });
});
