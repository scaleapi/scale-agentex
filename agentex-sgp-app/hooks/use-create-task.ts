'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { agentRPCNonStreaming } from 'agentex/lib';

import { tasksKeys } from './use-tasks';

import type AgentexSDK from 'agentex';
import type { Task } from 'agentex/resources';

type CreateTaskParams = {
  agentName: string;
  name?: string;
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
      // name,
      params,
    }: CreateTaskParams): Promise<Task> => {
      const response = await agentRPCNonStreaming(
        agentexClient,
        { agentName },
        'task/create',
        {
          // TODO: Theres a crazy backend error where if you create two tasks with teh same name, it
          // returns the same task id for the second one rather than creating a new task.
          // Uncomment this once that bug is fixed.
          // name: name ?? null,
          params: params ?? {},
        }
      );

      if (response.error != null) {
        throw new Error(response.error.message);
      }

      return response.result;
    },
    onSuccess: newTask => {
      // Add new task to the unfiltered cache
      queryClient.setQueryData<Task[]>(tasksKeys.all, old => {
        if (!old) return [newTask];
        // Avoid duplicates
        if (old.some(t => t.id === newTask.id)) {
          return old;
        }
        return [...old, newTask]; // Add to end (will be reversed in UI to show first)
      });

      // Invalidate all task queries to ensure consistency
      queryClient.invalidateQueries({ queryKey: tasksKeys.all });
    },
  });
}
