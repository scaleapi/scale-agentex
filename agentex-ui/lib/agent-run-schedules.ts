export type ScheduleInitialInput = {
  type: 'text';
  author: 'user';
  content: string;
};

export type AgentRunSchedule = {
  id: string;
  agent_id: string;
  name: string;
  description: string | null;
  cron_expression: string | null;
  interval_seconds: number | null;
  timezone: string;
  start_at: string | null;
  end_at: string | null;
  paused: boolean;
  task_params: Record<string, unknown> | null;
  task_metadata: Record<string, unknown> | null;
  initial_input: ScheduleInitialInput;
  initial_input_method: string;
  created_at: string | null;
  updated_at: string | null;
  state: 'ACTIVE' | 'PAUSED';
  next_action_times: string[];
  skipped_action_times: string[];
  last_action_time: string | null;
  num_actions_taken: number;
};

export type CreateAgentRunScheduleRequest = {
  name: string;
  description?: string | null;
  cron_expression?: string | null;
  interval_seconds?: number | null;
  timezone?: string;
  paused?: boolean;
  initial_input: ScheduleInitialInput;
  task_params?: Record<string, unknown> | null;
  task_metadata?: Record<string, unknown> | null;
};

export type UpdateAgentRunScheduleRequest = Partial<
  Omit<CreateAgentRunScheduleRequest, 'initial_input'> & {
    initial_input: ScheduleInitialInput;
  }
>;

type AgentRunScheduleResponse = {
  id: string;
  agent_id: string;
  name: string;
  initial_input: {
    content: string;
    author?: string;
    type?: 'text';
  };
  initial_input_method: string;
  description?: string | null;
  cron_expression?: string | null;
  interval_seconds?: number | null;
  timezone?: string;
  start_at?: string | null;
  end_at?: string | null;
  paused?: boolean;
  task_params?: Record<string, unknown> | null;
  task_metadata?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  state?: 'ACTIVE' | 'PAUSED';
  next_action_times?: string[];
  skipped_action_times?: string[];
  last_action_time?: string | null;
  num_actions_taken?: number;
};

export function normalizeAgentRunSchedule(
  schedule: AgentRunScheduleResponse
): AgentRunSchedule {
  return {
    id: schedule.id,
    agent_id: schedule.agent_id,
    name: schedule.name,
    description: schedule.description ?? null,
    cron_expression: schedule.cron_expression ?? null,
    interval_seconds: schedule.interval_seconds ?? null,
    timezone: schedule.timezone ?? 'UTC',
    start_at: schedule.start_at ?? null,
    end_at: schedule.end_at ?? null,
    paused: schedule.paused ?? false,
    task_params: schedule.task_params ?? null,
    task_metadata: schedule.task_metadata ?? null,
    initial_input: {
      type: 'text',
      author: 'user',
      content: schedule.initial_input.content,
    },
    initial_input_method: schedule.initial_input_method,
    created_at: schedule.created_at ?? null,
    updated_at: schedule.updated_at ?? null,
    state: schedule.state ?? 'ACTIVE',
    next_action_times: schedule.next_action_times ?? [],
    skipped_action_times: schedule.skipped_action_times ?? [],
    last_action_time: schedule.last_action_time ?? null,
    num_actions_taken: schedule.num_actions_taken ?? 0,
  };
}
