import { describe, expect, it } from 'vitest';

import { normalizeAgentRunSchedule } from './agent-run-schedules';

describe('normalizeAgentRunSchedule', () => {
  it('fills SDK-optional schedule fields with UI defaults', () => {
    expect(
      normalizeAgentRunSchedule({
        id: 'schedule-1',
        agent_id: 'agent-1',
        name: 'daily-summary',
        initial_input: { content: 'Summarize today' },
        initial_input_method: 'event/send',
      })
    ).toMatchObject({
      description: null,
      cron_expression: null,
      interval_seconds: null,
      timezone: 'UTC',
      paused: false,
      state: 'ACTIVE',
      next_action_times: [],
      skipped_action_times: [],
      num_actions_taken: 0,
      initial_input: {
        type: 'text',
        author: 'user',
        content: 'Summarize today',
      },
    });
  });
});
