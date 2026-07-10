import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { toast } from '@/components/ui/toast';
import {
  type AgentRunSchedule,
  type CreateAgentRunScheduleRequest,
  normalizeAgentRunSchedule,
  type UpdateAgentRunScheduleRequest,
} from '@/lib/agent-run-schedules';

import type AgentexSDK from 'agentex';
import type { Agent } from 'agentex/resources';

export const scheduleKeys = {
  all: ['agentRunSchedules'] as const,
  byAgentId: (agentId: string | null) =>
    agentId
      ? ([...scheduleKeys.all, 'agent', agentId] as const)
      : scheduleKeys.all,
  detail: (agentId: string, scheduleId: string) =>
    [...scheduleKeys.byAgentId(agentId), 'detail', scheduleId] as const,
};

type ScheduleMutationContext = {
  agentexClient: AgentexSDK;
  agentId: string;
};

type ScheduleActionInput =
  | string
  | {
      scheduleId: string;
      scheduledTime: string;
    };

export type AgentRunScheduleListItem = {
  agentId: string;
  schedule: AgentRunSchedule;
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Please try again.';
}

export function useAgentRunSchedules(
  agentexClient: AgentexSDK,
  agentId: string | null
) {
  return useQuery({
    queryKey: scheduleKeys.byAgentId(agentId),
    queryFn: async () => {
      if (!agentId) {
        return [];
      }
      const response = await agentexClient.agents.schedules.list(agentId, {
        limit: 100,
      });
      return response.run_schedules.map(normalizeAgentRunSchedule);
    },
    enabled: !!agentId,
  });
}

export function useAgentRunSchedulesForAgents(
  agentexClient: AgentexSDK,
  agents: Agent[],
  enabled: boolean
) {
  return useQueries({
    queries: agents.map(agent => ({
      queryKey: scheduleKeys.byAgentId(agent.id),
      queryFn: async () => {
        const response = await agentexClient.agents.schedules.list(agent.id, {
          limit: 100,
        });
        return response.run_schedules.map(normalizeAgentRunSchedule);
      },
      enabled,
    })),
  });
}

export function useAgentRunScheduleDetailsForItems(
  agentexClient: AgentexSDK,
  items: AgentRunScheduleListItem[]
) {
  return useQueries({
    queries: items.map(({ agentId, schedule }) => ({
      queryKey: scheduleKeys.detail(agentId, schedule.id),
      queryFn: async () =>
        normalizeAgentRunSchedule(
          await agentexClient.agents.schedules.retrieve(schedule.id, {
            agent_id: agentId,
          })
        ),
      staleTime: 30_000,
    })),
  });
}

export function useCreateAgentRunSchedule({
  agentexClient,
  agentId,
}: ScheduleMutationContext) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CreateAgentRunScheduleRequest) =>
      normalizeAgentRunSchedule(
        await agentexClient.agents.schedules.create(agentId, payload)
      ),
    onSuccess: schedule => {
      queryClient.invalidateQueries({
        queryKey: scheduleKeys.byAgentId(agentId),
      });
      queryClient.setQueryData(
        scheduleKeys.detail(agentId, schedule.id),
        schedule
      );
    },
    onError: error => {
      toast.error({
        title: 'Failed to create scheduled task',
        message: errorMessage(error),
      });
    },
  });
}

export function useUpdateAgentRunSchedule({
  agentexClient,
  agentId,
}: ScheduleMutationContext) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      scheduleId,
      payload,
    }: {
      scheduleId: string;
      payload: UpdateAgentRunScheduleRequest;
    }) =>
      agentexClient.agents.schedules
        .update(scheduleId, { agent_id: agentId, ...payload })
        .then(normalizeAgentRunSchedule),
    onSuccess: schedule => {
      queryClient.invalidateQueries({
        queryKey: scheduleKeys.byAgentId(agentId),
      });
      queryClient.setQueryData(
        scheduleKeys.detail(agentId, schedule.id),
        schedule
      );
      toast.success('Scheduled task updated');
    },
    onError: error => {
      toast.error({
        title: 'Failed to update scheduled task',
        message: errorMessage(error),
      });
    },
  });
}

export function useScheduleAction({
  agentexClient,
  agentId,
  action,
}: ScheduleMutationContext & {
  action: 'delete' | 'pause' | 'resume' | 'skip' | 'trigger' | 'unskip';
}) {
  const queryClient = useQueryClient();

  return useMutation<
    AgentRunSchedule | { id: string; message: string },
    Error,
    ScheduleActionInput
  >({
    mutationFn: input => {
      const scheduleId = typeof input === 'string' ? input : input.scheduleId;
      const scheduledTime =
        typeof input === 'string' ? undefined : input.scheduledTime;
      switch (action) {
        case 'delete':
          return agentexClient.agents.schedules.delete(scheduleId, {
            agent_id: agentId,
          });
        case 'pause':
          return agentexClient.agents.schedules
            .pause(scheduleId, { agent_id: agentId })
            .then(normalizeAgentRunSchedule);
        case 'resume':
          return agentexClient.agents.schedules
            .resume(scheduleId, { agent_id: agentId })
            .then(normalizeAgentRunSchedule);
        case 'skip':
          if (!scheduledTime) {
            throw new Error('scheduledTime is required to skip a run');
          }
          return agentexClient.agents.schedules
            .skip(scheduleId, {
              agent_id: agentId,
              scheduled_time: scheduledTime,
            })
            .then(normalizeAgentRunSchedule);
        case 'trigger':
          return agentexClient.agents.schedules
            .trigger(scheduleId, { agent_id: agentId })
            .then(normalizeAgentRunSchedule);
        case 'unskip':
          if (!scheduledTime) {
            throw new Error('scheduledTime is required to unskip a run');
          }
          return agentexClient.agents.schedules
            .unskip(scheduleId, {
              agent_id: agentId,
              scheduled_time: scheduledTime,
            })
            .then(normalizeAgentRunSchedule);
      }
    },
    onSuccess: result => {
      queryClient.invalidateQueries({
        queryKey: scheduleKeys.byAgentId(agentId),
      });
      if ('id' in result) {
        queryClient.invalidateQueries({
          queryKey: scheduleKeys.detail(agentId, result.id),
        });
      }
      toast.success(
        action === 'trigger'
          ? 'Scheduled task triggered'
          : action === 'skip'
            ? 'Scheduled run skipped'
            : action === 'unskip'
              ? 'Scheduled run restored'
              : `Scheduled task ${action === 'delete' ? 'deleted' : `${action}d`}`
      );
    },
    onError: error => {
      toast.error({
        title: `Failed to ${action} scheduled task`,
        message: errorMessage(error),
      });
    },
  });
}
