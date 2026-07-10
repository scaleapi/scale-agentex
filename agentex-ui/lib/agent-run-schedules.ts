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

export type AgentRunScheduleListResponse = {
  run_schedules: AgentRunSchedule[];
  total: number;
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

async function request<T>(
  baseURL: string,
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${baseURL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function schedulesPath(agentId: string) {
  return `/agents/${encodeURIComponent(agentId)}/schedules`;
}

export const agentRunSchedulesAPI = {
  list: (baseURL: string, agentId: string) =>
    request<AgentRunScheduleListResponse>(
      baseURL,
      `${schedulesPath(agentId)}?limit=100`
    ),

  get: (baseURL: string, agentId: string, scheduleId: string) =>
    request<AgentRunSchedule>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}`
    ),

  create: (
    baseURL: string,
    agentId: string,
    payload: CreateAgentRunScheduleRequest
  ) =>
    request<AgentRunSchedule>(baseURL, schedulesPath(agentId), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  update: (
    baseURL: string,
    agentId: string,
    scheduleId: string,
    payload: UpdateAgentRunScheduleRequest
  ) =>
    request<AgentRunSchedule>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }
    ),

  delete: (baseURL: string, agentId: string, scheduleId: string) =>
    request<{ id: string; message: string }>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}`,
      { method: 'DELETE' }
    ),

  pause: (baseURL: string, agentId: string, scheduleId: string) =>
    request<AgentRunSchedule>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}/pause`,
      { method: 'POST', body: JSON.stringify({}) }
    ),

  resume: (baseURL: string, agentId: string, scheduleId: string) =>
    request<AgentRunSchedule>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}/resume`,
      { method: 'POST', body: JSON.stringify({}) }
    ),

  trigger: (baseURL: string, agentId: string, scheduleId: string) =>
    request<AgentRunSchedule>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}/trigger`,
      { method: 'POST' }
    ),

  skip: (
    baseURL: string,
    agentId: string,
    scheduleId: string,
    scheduledTime: string
  ) =>
    request<AgentRunSchedule>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}/skip`,
      {
        method: 'POST',
        body: JSON.stringify({ scheduled_time: scheduledTime }),
      }
    ),

  unskip: (
    baseURL: string,
    agentId: string,
    scheduleId: string,
    scheduledTime: string
  ) =>
    request<AgentRunSchedule>(
      baseURL,
      `${schedulesPath(agentId)}/${encodeURIComponent(scheduleId)}/unskip`,
      {
        method: 'POST',
        body: JSON.stringify({ scheduled_time: scheduledTime }),
      }
    ),
};
