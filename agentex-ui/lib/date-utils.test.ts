import { describe, it, expect } from 'vitest';

import { calculateThinkingTime } from '@/lib/date-utils';

import type { TaskMessage } from 'agentex/resources';

describe('calculateThinkingTime', () => {
  it('calculates time difference in seconds', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:05.000Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBe(5);
  });

  it('rounds to 1 decimal place for times under 10 seconds', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:02.456Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBe(2.5); // 2.456 rounded to 1 decimal
  });

  it('rounds to nearest second for times 10 seconds or more', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:15.789Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBe(16); // 15.789 rounded to nearest second
  });

  it('returns null when message.created_at is null', () => {
    const message = {
      created_at: null,
    } as unknown as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:05.000Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBeNull();
  });

  it('returns null when message.created_at is undefined', () => {
    const message = {} as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:05.000Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBeNull();
  });

  it('returns null when nextBlockTimestamp is null', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = null as unknown as string;

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBeNull();
  });

  it('returns null when nextBlockTimestamp is undefined', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = undefined as unknown as string;

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBeNull();
  });

  it('handles millisecond precision correctly', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:00.500Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBe(0.5);
  });

  it('handles very small time differences', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:00.100Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBe(0.1);
  });

  it('handles time difference exactly at 10 seconds', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:00:10.000Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBe(10);
  });

  it('handles large time differences', () => {
    const message = {
      created_at: '2024-01-01T00:00:00.000Z',
    } as TaskMessage;
    const nextBlockTimestamp = '2024-01-01T00:05:00.000Z';

    const result = calculateThinkingTime(message, nextBlockTimestamp);
    expect(result).toBe(300); // 5 minutes = 300 seconds
  });
});
