import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { toast } from '@/components/ui/toast';
import {
  agentRunSchedulesAPI,
  type AgentRunSchedule,
  type CreateAgentRunScheduleRequest,
  type UpdateAgentRunScheduleRequest,
} from '@/lib/agent-run-schedules';

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
  baseURL: string;
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

export function useAgentRunSchedules(baseURL: string, agentId: string | null) {
  return useQuery({
    queryKey: scheduleKeys.byAgentId(agentId),
    queryFn: async () => {
      if (!agentId) {
        return [];
      }
      const response = await agentRunSchedulesAPI.list(baseURL, agentId);
      return response.run_schedules;
    },
    enabled: !!agentId,
  });
}

export function useAgentRunSchedulesForAgents(
  baseURL: string,
  agents: Agent[],
  enabled: boolean
) {
  return useQueries({
    queries: agents.map(agent => ({
      queryKey: scheduleKeys.byAgentId(agent.id),
      queryFn: async () => {
        const response = await agentRunSchedulesAPI.list(baseURL, agent.id);
        return response.run_schedules;
      },
      enabled,
    })),
  });
}

export function useAgentRunScheduleDetailsForItems(
  baseURL: string,
  items: AgentRunScheduleListItem[]
) {
  return useQueries({
    queries: items.map(({ agentId, schedule }) => ({
      queryKey: scheduleKeys.detail(agentId, schedule.id),
      queryFn: () => agentRunSchedulesAPI.get(baseURL, agentId, schedule.id),
      staleTime: 30_000,
    })),
  });
}

export function useCreateAgentRunSchedule({
  baseURL,
  agentId,
}: ScheduleMutationContext) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateAgentRunScheduleRequest) =>
      agentRunSchedulesAPI.create(baseURL, agentId, payload),
    onSuccess: schedule => {
      queryClient.invalidateQueries({
        queryKey: scheduleKeys.byAgentId(agentId),
      });
      queryClient.setQueryData(
        scheduleKeys.detail(agentId, schedule.id),
        schedule
      );
      toast.success('Scheduled task created');
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
  baseURL,
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
    }) => agentRunSchedulesAPI.update(baseURL, agentId, scheduleId, payload),
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
  baseURL,
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
          return agentRunSchedulesAPI.delete(baseURL, agentId, scheduleId);
        case 'pause':
          return agentRunSchedulesAPI.pause(baseURL, agentId, scheduleId);
        case 'resume':
          return agentRunSchedulesAPI.resume(baseURL, agentId, scheduleId);
        case 'skip':
          if (!scheduledTime) {
            throw new Error('scheduledTime is required to skip a run');
          }
          return agentRunSchedulesAPI.skip(
            baseURL,
            agentId,
            scheduleId,
            scheduledTime
          );
        case 'trigger':
          return agentRunSchedulesAPI.trigger(baseURL, agentId, scheduleId);
        case 'unskip':
          if (!scheduledTime) {
            throw new Error('scheduledTime is required to unskip a run');
          }
          return agentRunSchedulesAPI.unskip(
            baseURL,
            agentId,
            scheduleId,
            scheduledTime
          );
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
