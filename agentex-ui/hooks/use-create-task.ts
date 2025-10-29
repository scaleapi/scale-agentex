'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { agentRPCNonStreaming } from 'agentex/lib';

import { toast } from '@/components/agentex/toast';

import { tasksKeys } from './use-tasks';

import type AgentexSDK from 'agentex';
import type { Task } from 'agentex/resources';

type CreateTaskParams = {
  agentName: string;
  params?: Record<string, unknown>;
};

/**
 * Creates a new task for a given agent
 */
export function useCreateTask({
  agentexClient,
}: {
  agentexClient: AgentexSDK;
}) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      agentName,
      params,
    }: CreateTaskParams): Promise<Task> => {
      const response = await agentRPCNonStreaming(
        agentexClient,
        { agentName },
        'task/create',
        {
          params: params ?? {},
        }
      );

      if (response.error != null) {
        throw new Error(response.error.message);
      }

      return response.result;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: tasksKeys.all });
      queryClient.invalidateQueries({
        queryKey: tasksKeys.byAgentName(variables.agentName),
      });
    },
    onError: error => {
      toast.error({
        title: 'Failed to create task',
        message: error instanceof Error ? error.message : 'Please try again.',
      });
    },
  });
}
