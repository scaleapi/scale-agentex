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

export function useAgentRunScheduleDetails(
  baseURL: string,
  agentId: string | null,
  schedules: AgentRunSchedule[]
) {
  return useQueries({
    queries:
      agentId == null
        ? []
        : schedules.map(schedule => ({
            queryKey: scheduleKeys.detail(agentId, schedule.id),
            queryFn: () =>
              agentRunSchedulesAPI.get(baseURL, agentId, schedule.id),
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
  action: 'delete' | 'pause' | 'resume' | 'trigger';
}) {
  const queryClient = useQueryClient();

  return useMutation<
    AgentRunSchedule | { id: string; message: string },
    Error,
    string
  >({
    mutationFn: (scheduleId: string) => {
      switch (action) {
        case 'delete':
          return agentRunSchedulesAPI.delete(baseURL, agentId, scheduleId);
        case 'pause':
          return agentRunSchedulesAPI.pause(baseURL, agentId, scheduleId);
        case 'resume':
          return agentRunSchedulesAPI.resume(baseURL, agentId, scheduleId);
        case 'trigger':
          return agentRunSchedulesAPI.trigger(baseURL, agentId, scheduleId);
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
