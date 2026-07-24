import { describe, it, expect } from 'vitest';

import { createTaskName } from '@/lib/task-utils';

import type { TaskListResponse } from 'agentex/resources';

describe('createTaskName', () => {
  it('returns task_metadata.display_name when present', () => {
    const task = {
      id: '123',
      task_metadata: { display_name: 'My task' },
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('My task');
  });

  it('strips the legacy scheduled-message prefix from display_name', () => {
    const task = {
      id: '123',
      task_metadata: {
        display_name: 'Scheduled Message: Daily digest',
        schedule_id: 'sched-1',
      },
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Daily digest');
  });

  it('falls back to the task name when there is no display_name', () => {
    const task = {
      id: '123',
      name: 'my-task-name',
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('my-task-name');
  });

  it('returns "Unnamed task" when neither display_name nor name is set', () => {
    const task = {
      id: '123',
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });

  it('returns "Unnamed task" when name is an empty string', () => {
    const task = {
      id: '123',
      name: '',
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });
});
