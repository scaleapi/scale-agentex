import { describe, it, expect } from 'vitest';

import { createTaskName } from '@/lib/task-utils';

import type { TaskListResponse } from 'agentex/resources';

describe('createTaskName', () => {
  it('returns description when params.description is a string', () => {
    const task = {
      id: '123',
      params: {
        description: 'Test task description',
      },
    } as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Test task description');
  });

  it('returns "Unnamed task" when params.description is missing', () => {
    const task = {
      params: {},
    } as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });

  it('returns "Unnamed task" when params is missing', () => {
    const task = {} as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });

  it('returns "Unnamed task" when params.description is not a string', () => {
    const task = {
      params: {
        description: 123,
      },
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });

  it('returns "Unnamed task" when params.description is null', () => {
    const task = {
      params: {
        description: null,
      },
    } as unknown as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });

  it('returns "Unnamed task" when params.description is undefined', () => {
    const task = {
      id: '123',
      params: {
        description: undefined,
      },
    } as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });

  it('returns "Unnamed task" for empty string description', () => {
    const task = {
      id: '123',
      params: {
        description: '',
      },
    } as TaskListResponse.TaskListResponseItem;

    expect(createTaskName(task)).toBe('Unnamed task');
  });
});
