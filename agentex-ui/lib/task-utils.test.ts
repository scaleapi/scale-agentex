import { describe, it, expect } from 'vitest';

import { createTaskName, deriveTaskDisplayName } from '@/lib/task-utils';

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

describe('deriveTaskDisplayName', () => {
  it('returns a short prompt unchanged', () => {
    expect(deriveTaskDisplayName('say hello')).toBe('say hello');
  });

  it('trims surrounding whitespace', () => {
    expect(deriveTaskDisplayName('  say hello \n')).toBe('say hello');
  });

  it('collapses internal whitespace and newlines to single spaces', () => {
    expect(deriveTaskDisplayName('summarize\nthis   report\tplease')).toBe(
      'summarize this report please'
    );
  });

  it('truncates to 80 characters', () => {
    const prompt = 'a'.repeat(100);
    expect(deriveTaskDisplayName(prompt)).toBe('a'.repeat(80));
  });

  it('produces a label createTaskName resolves for a UI-created task', () => {
    // Writer/reader contract: a task shaped like the prompt-input writer's
    // output (display_name set, name null) must not render as "Unnamed task".
    const task = {
      id: '123',
      name: null,
      task_metadata: { display_name: deriveTaskDisplayName('say hello') },
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('say hello');
  });
});
