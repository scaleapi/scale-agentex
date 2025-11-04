'use client';

import {
  InfiniteData,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { agentRPCNonStreaming } from 'agentex/lib';

import { toast } from '@/components/agentex/toast';
import { tasksKeys } from '@/hooks/use-tasks';

import type AgentexSDK from 'agentex';
import type {
  Agent,
  Task,
  TaskListResponse,
  TaskRetrieveResponse,
} from 'agentex/resources';

/**
 * Updates a task within an infinite query cache structure for optimistic updates.
 *
 * If the task exists in any page, updates it in place. Otherwise, adds it to the top
 * of the first page with a temporary agent object attached for display purposes.
 *
 * @param task - Task - The task entity to update or insert
 * @param agentName - string - The name of the agent associated with this task
 * @param data - InfiniteData<TaskListResponse> | undefined - Current paginated task list cache data
 * @returns InfiniteData<TaskListResponse> | undefined - Updated cache data with the task included
 */
export function updateTaskInInfiniteQuery(
  task: Task,
  agentName: string,
  data: InfiniteData<TaskListResponse> | undefined
): InfiniteData<TaskListResponse> | undefined {
  if (!data) return undefined;

  if (data.pages.some(page => page.some(t => t.id === task.id))) {
    return {
      pages: data.pages.map(page =>
        page.map(t =>
          t.id === task.id ? { ...task, agents: t.agents || null } : t
        )
      ),
      pageParams: data.pageParams,
    };
  }

  // Create a dummy agent to add to the task
  const agent: Agent = {
    id: '1',
    name: agentName,
    description: '',
    acp_type: 'agentic',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  const taskWithAgentName: TaskListResponse.TaskListResponseItem = {
    ...task,
    agents: [agent],
  };

  // Add the new task to the top of the first page
  const newPages = [...data.pages];
  if (newPages.length > 0 && newPages[0]) {
    newPages[0] = [taskWithAgentName, ...newPages[0]];
  } else {
    newPages[0] = [taskWithAgentName];
  }

  return {
    pages: newPages,
    pageParams: data.pageParams,
  };
}

type CreateTaskParams = {
  agentName: string;
  params?: Record<string, unknown>;
};

/**
 * Creates a new task for an agent via the Agentex RPC API.
 *
 * On success, automatically updates all relevant React Query caches (individual task,
 * all tasks list, agent-specific tasks list) for immediate UI updates. On error,
 * displays a user-facing toast notification.
 *
 * @param agentexClient - AgentexSDK - The SDK client used to send the task creation request
 * @returns UseMutationResult<Task, Error, CreateTaskParams> - Mutation object with mutate/mutateAsync functions
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
    onSuccess: (task, variables) => {
      queryClient.setQueryData<TaskRetrieveResponse>(
        tasksKeys.individualById(task.id),
        task
      );
      queryClient.setQueryData<InfiniteData<TaskListResponse>>(
        tasksKeys.all,
        data => updateTaskInInfiniteQuery(task, variables.agentName, data)
      );
      queryClient.setQueryData<InfiniteData<TaskListResponse>>(
        tasksKeys.byAgentName(variables.agentName),
        data => updateTaskInInfiniteQuery(task, variables.agentName, data)
      );
    },
    onError: error => {
      toast.error({
        title: 'Failed to create task',
        message: error instanceof Error ? error.message : 'Please try again.',
      });
    },
  });
}
