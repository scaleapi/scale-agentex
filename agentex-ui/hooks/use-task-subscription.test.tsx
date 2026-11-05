import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { subscribeTaskState } from '@/hooks/custom-subscribe-task-state';
import { spansKeys } from '@/hooks/use-spans';

import { useTaskSubscription } from './use-task-subscription';

import type AgentexSDK from 'agentex';
import type { TaskMessage } from 'agentex/resources';

vi.mock('@/hooks/custom-subscribe-task-state', () => ({
  subscribeTaskState: vi.fn(() => new Promise(() => {})),
}));

type MessagesListener = { onMessagesChange: (messages: TaskMessage[]) => void };

describe('useTaskSubscription', () => {
  it('invalidates the cached spans for the task once streaming finishes', async () => {
    const taskId = 'task-1';
    // Matches the app's QueryClient: cached queries never go stale on their own,
    // so the Traces tab only refetches when this invalidation reaches its key.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData(spansKeys.byTaskId(taskId), []);

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    renderHook(
      () =>
        useTaskSubscription({
          agentexClient: {} as AgentexSDK,
          taskId,
          agentName: 'agent',
        }),
      { wrapper }
    );

    await waitFor(() => expect(subscribeTaskState).toHaveBeenCalled());
    const listener = vi.mocked(subscribeTaskState).mock
      .calls[0]![2] as unknown as MessagesListener;

    listener.onMessagesChange([
      { id: 'm1', task_id: taskId, streaming_status: 'DONE' } as TaskMessage,
    ]);

    expect(
      queryClient.getQueryState(spansKeys.byTaskId(taskId))?.isInvalidated
    ).toBe(true);
  });
});
