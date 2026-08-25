import { createRef } from 'react';

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TaskMessages } from './task-messages';

import type { TaskMessage } from 'agentex/resources';

const useTaskMessagesMock = vi.fn();
const useTaskMock = vi.fn();

vi.mock('@/components/providers', () => ({
  useAgentexClient: () => ({ agentexClient: {}, sgpAppURL: '' }),
}));
vi.mock('@/hooks/use-safe-search-params', () => ({
  useSafeSearchParams: () => ({ agentName: 'my-agent' }),
}));
vi.mock('@/hooks/use-agents', () => ({
  useAgents: () => ({ data: [] }),
}));
vi.mock('@/hooks/use-task-messages', () => ({
  useTaskMessages: () => useTaskMessagesMock(),
}));
vi.mock('@/hooks/use-tasks', () => ({
  useTask: () => useTaskMock(),
}));

/** What a failed turn actually leaves behind: a user message, no reply. */
const USER_MESSAGE = {
  id: 'user-1',
  task_id: 'task-1',
  content: { type: 'text', author: 'user', content: 'hello' },
  streaming_status: 'DONE',
  created_at: '2026-08-24T00:00:00.000Z',
  updated_at: '2026-08-24T00:00:00.000Z',
} as unknown as TaskMessage;

function renderForTaskStatus(status: string) {
  useTaskMessagesMock.mockReturnValue({
    messages: [USER_MESSAGE],
    // What the subscription writes on a cold load — no client-local error.
    rpcStatus: 'success',
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
  });
  useTaskMock.mockReturnValue({ data: { id: 'task-1', status } });

  return render(
    <TaskMessages
      taskId="task-1"
      headerRef={createRef<HTMLDivElement>()}
      scrollContainerRef={createRef<HTMLDivElement>()}
    />
  );
}

// ShimmeringText renders one span per character, so query the concatenated text.
const THINKING = 'Thinking ...';

describe('TaskMessages thinking indicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows while a running task has no reply yet', () => {
    const { container } = renderForTaskStatus('RUNNING');
    expect(container.textContent).toContain(THINKING);
  });

  it.each(['FAILED', 'CANCELED', 'TERMINATED', 'TIMED_OUT', 'COMPLETED'])(
    'hides on a %s task loaded with no client-local error state',
    status => {
      const { container } = renderForTaskStatus(status);
      expect(container.textContent).not.toContain(THINKING);
    }
  );
});
