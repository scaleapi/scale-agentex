'use client';

import {
  InfiniteData,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { agentRPCNonStreaming } from 'agentex/lib';

import { toast } from '@/components/agentex/toast';

import { tasksKeys } from './use-tasks';

import type AgentexSDK from 'agentex';
import type { Task, TaskListResponse } from 'agentex/resources';

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
    onSuccess: (newTask, variables) => {
      // Helper function to update infinite query cache
      const updateInfiniteCache = (queryKey: readonly unknown[]) => {
        queryClient.setQueryData<InfiniteData<TaskListResponse>>(
          queryKey,
          old => {
            if (!old) {
              // If no cache exists, create initial structure
              return {
                pages: [[newTask]],
                pageParams: [1],
              };
            }

            // Add new task to the first page (prepend to show at top)
            const firstPage = old.pages[0] ?? [];
            if (firstPage.some(t => t.id === newTask.id)) {
              return old; // Avoid duplicates
            }

            return {
              ...old,
              pages: [[newTask, ...firstPage], ...old.pages.slice(1)],
            };
          }
        );
      };

      // Update both the agent-specific cache and the generic "all tasks" cache
      updateInfiniteCache(tasksKeys.byAgentName(variables.agentName));
      updateInfiniteCache(tasksKeys.all);

      // Invalidate all task queries to ensure consistency
      queryClient.invalidateQueries({ queryKey: tasksKeys.all });
    },
    onError: error => {
      toast.error({
        title: 'Failed to create task',
        message: error instanceof Error ? error.message : 'Please try again.',
      });
    },
  });
}
