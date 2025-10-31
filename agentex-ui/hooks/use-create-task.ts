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
