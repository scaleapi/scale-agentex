import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { agentRPCNonStreaming } from 'agentex/lib';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCreateTask } from './use-create-task';

import type AgentexSDK from 'agentex';

vi.mock('agentex/lib', () => ({
  agentRPCNonStreaming: vi.fn(),
}));

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function mockCreatedTask(task: Record<string, unknown>) {
  vi.mocked(agentRPCNonStreaming).mockResolvedValue({
    jsonrpc: '2.0',
    id: 'rpc-1',
    result: task,
    error: null,
  } as never);
}

describe('useCreateTask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('forwards task_metadata in the task/create request body', async () => {
    mockCreatedTask({
      id: 'task-1',
      name: null,
      task_metadata: { display_name: 'say hello' },
    });
    const agentexClient = {} as unknown as AgentexSDK;
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderHook(() => useCreateTask({ agentexClient }), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({
        agentName: 'my-agent',
        params: { description: 'say hello', content: 'say hello' },
        task_metadata: { display_name: 'say hello' },
      });
    });

    expect(agentRPCNonStreaming).toHaveBeenCalledWith(
      agentexClient,
      { agentName: 'my-agent' },
      'task/create',
      {
        params: { description: 'say hello', content: 'say hello' },
        task_metadata: { display_name: 'say hello' },
      }
    );
  });

  it('sends null task_metadata when none is provided', async () => {
    mockCreatedTask({ id: 'task-2', name: null, task_metadata: null });
    const agentexClient = {} as unknown as AgentexSDK;
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderHook(() => useCreateTask({ agentexClient }), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({
        agentName: 'my-agent',
        params: { description: 'say hello' },
      });
    });

    expect(agentRPCNonStreaming).toHaveBeenCalledWith(
      agentexClient,
      { agentName: 'my-agent' },
      'task/create',
      {
        params: { description: 'say hello' },
        task_metadata: null,
      }
    );
  });
});
