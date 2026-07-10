import { describe, expect, it } from 'vitest';

import {
  cadenceToPayload,
  generateScheduleName,
  normalizeScheduleName,
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
