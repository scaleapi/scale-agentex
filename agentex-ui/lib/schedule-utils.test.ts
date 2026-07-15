import { describe, expect, it } from 'vitest';

import {
  cadenceToPayload,
  describeCadence,
  describeCadenceConfig,
  generateScheduleName,
  getCadenceValidationError,
  normalizeScheduleName,
  sanitizeScheduleNameInput,
  scheduleToCadence,
  type CadenceConfig,
} from './schedule-utils';

import type { AgentRunSchedule } from './agent-run-schedules';

describe('generateScheduleName', () => {
  it('slugifies prompt text', () => {
    expect(generateScheduleName('Daily Granola summary!', [])).toBe(
      'daily-granola-summary'
    );
  });

  it('adds a suffix when the name already exists', () => {
    expect(
      generateScheduleName('Daily Granola summary', [
        { name: 'daily-granola-summary' },
      ])
    ).toBe('daily-granola-summary-2');
  });

  it('falls back for empty prompts', () => {
    expect(generateScheduleName('', [])).toBe('scheduled-task');
  });
});

describe('normalizeScheduleName', () => {
  it('keeps editable names within backend slug constraints', () => {
    expect(normalizeScheduleName('  Daily Summary!!! ')).toBe('daily-summary');
  });

  it('preserves a trailing hyphen while editing', () => {
    expect(sanitizeScheduleNameInput('daily-')).toBe('daily-');
    expect(sanitizeScheduleNameInput('Daily- Summary')).toBe('daily-summary');
  });
});

describe('cadenceToPayload', () => {
  const base: CadenceConfig = {
    type: 'daily',
    time: '09:30',
    dayOfWeek: 'MON',
    dayOfMonth: '1',
    intervalValue: '1',
    intervalUnit: 'hours',
  };

  it('converts daily cadence to cron', () => {
    expect(cadenceToPayload(base)).toEqual({ cron_expression: '30 9 * * *' });
  });

  it('converts weekly cadence to cron', () => {
    expect(cadenceToPayload({ ...base, type: 'weekly' })).toEqual({
      cron_expression: '30 9 * * MON',
    });
  });

  it('converts monthly cadence to cron', () => {
    expect(
      cadenceToPayload({ ...base, type: 'monthly', dayOfMonth: '15' })
    ).toEqual({
      cron_expression: '30 9 15 * *',
    });
  });

  it('converts interval cadence to seconds', () => {
    expect(
      cadenceToPayload({
        ...base,
        type: 'interval',
        intervalValue: '2',
        intervalUnit: 'hours',
      })
    ).toEqual({ interval_seconds: 7200 });
  });

  it('rejects malformed interval and monthly values instead of coercing them', () => {
    const malformedInterval = {
      ...base,
      type: 'interval',
      intervalValue: '1sss',
    } satisfies CadenceConfig;
    expect(getCadenceValidationError(malformedInterval)).toBe(
      'Enter a whole-number interval.'
    );
    expect(() => cadenceToPayload(malformedInterval)).toThrow(
      'Enter a whole-number interval.'
    );

    const invalidMonthDay = {
      ...base,
      type: 'monthly',
      dayOfMonth: '32',
    } satisfies CadenceConfig;
    expect(getCadenceValidationError(invalidMonthDay)).toBe(
      'Day of month must be between 1 and 31.'
    );
    expect(() => cadenceToPayload(invalidMonthDay)).toThrow(
      'Day of month must be between 1 and 31.'
    );
  });
});

describe('scheduleToCadence', () => {
  const schedule = {
    id: 'schedule-id',
    agent_id: 'agent-id',
    name: 'schedule',
    description: null,
    cron_expression: '30 9 * * MON',
    interval_seconds: null,
    timezone: 'UTC',
    start_at: null,
    end_at: null,
    paused: false,
    task_params: null,
    task_metadata: null,
    initial_input: { type: 'text', author: 'user', content: 'Run this' },
    initial_input_method: 'send_message',
    created_at: null,
    updated_at: null,
    state: 'ACTIVE',
    next_action_times: [],
    skipped_action_times: [],
    last_action_time: null,
    num_actions_taken: 0,
  } satisfies AgentRunSchedule;

  it('converts weekly cron to editable cadence config', () => {
    expect(scheduleToCadence(schedule)).toMatchObject({
      type: 'weekly',
      time: '09:30',
      dayOfWeek: 'MON',
    });
  });

  it('converts interval seconds to editable cadence config', () => {
    expect(
      scheduleToCadence({
        ...schedule,
        cron_expression: null,
        interval_seconds: 7200,
      })
    ).toMatchObject({
      type: 'interval',
      intervalValue: '2',
      intervalUnit: 'hours',
    });
  });
});

describe('describeCadence', () => {
  const schedule = {
    id: 'schedule-id',
    agent_id: 'agent-id',
    name: 'schedule',
    description: null,
    cron_expression: '30 9 * * *',
    interval_seconds: null,
    timezone: 'UTC',
    start_at: null,
    end_at: null,
    paused: false,
    task_params: null,
    task_metadata: null,
    initial_input: { type: 'text', author: 'user', content: 'Run this' },
    initial_input_method: 'send_message',
    created_at: null,
    updated_at: null,
    state: 'ACTIVE',
    next_action_times: [],
    skipped_action_times: [],
    last_action_time: null,
    num_actions_taken: 0,
  } satisfies AgentRunSchedule;

  it('describes common cron cadences in plain language', () => {
    expect(describeCadence(schedule)).toBe('Daily at 9:30 AM');
    expect(
      describeCadence({ ...schedule, cron_expression: '30 9 * * MON' })
    ).toBe('Every Monday at 9:30 AM');
    expect(
      describeCadence({ ...schedule, cron_expression: '30 9 15 * *' })
    ).toBe('Monthly on day 15 at 9:30 AM');
  });

  it('uses natural singular and plural interval units', () => {
    expect(
      describeCadence({
        ...schedule,
        cron_expression: null,
        interval_seconds: 3600,
      })
    ).toBe('Every 1 hour');
    expect(
      describeCadence({
        ...schedule,
        cron_expression: null,
        interval_seconds: 7200,
      })
    ).toBe('Every 2 hours');
  });

  it('uses the same singular interval formatting for editable cadence', () => {
    expect(
      describeCadenceConfig({
        type: 'interval',
        time: '09:00',
        dayOfWeek: 'MON',
        dayOfMonth: '1',
        intervalValue: '1',
        intervalUnit: 'minutes',
      })
    ).toBe('Every 1 minute');
  });
});
