import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { scheduleKeys, useScheduleAction } from './use-agent-run-schedules';

import type AgentexSDK from 'agentex';

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe('useScheduleAction', () => {
  it('removes a deleted schedule detail query instead of refetching it', async () => {
    const deleteSchedule = vi
      .fn()
      .mockResolvedValue({ id: 'schedule-1', message: 'deleted' });
    const agentexClient = {
      agents: { schedules: { delete: deleteSchedule } },
    } as unknown as AgentexSDK;
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const removeQueries = vi.spyOn(queryClient, 'removeQueries');
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries');
    const detailKey = scheduleKeys.detail('agent-1', 'schedule-1');
    queryClient.setQueryData(detailKey, { id: 'schedule-1' });

    const { result } = renderHook(
      () =>
        useScheduleAction({
          agentexClient,
          agentId: 'agent-1',
          action: 'delete',
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      await result.current.mutateAsync('schedule-1');
    });

    expect(removeQueries).toHaveBeenCalledWith({
      queryKey: detailKey,
      exact: true,
    });
    expect(queryClient.getQueryData(detailKey)).toBeUndefined();
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: scheduleKeys.byAgentId('agent-1'),
      exact: true,
    });
    expect(invalidateQueries).not.toHaveBeenCalledWith({
      queryKey: detailKey,
      exact: true,
    });
  });
});
