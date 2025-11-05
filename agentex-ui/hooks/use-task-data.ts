import { useQuery } from '@tanstack/react-query';

import type { TaskDataTables } from '@/lib/types';

async function fetchTaskData(taskId: string): Promise<TaskDataTables> {
  const response = await fetch(`/api/data/${taskId}`);

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ error: 'Unknown error' }));
    throw new Error(
      error.error || `Failed to fetch task data: ${response.statusText}`
    );
  }

  return response.json();
}

export function useTaskData(taskId: string | null) {
  return useQuery({
    queryKey: taskDataKeys.byTaskId(taskId!),
    queryFn: () => fetchTaskData(taskId!),
    enabled: !!taskId,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });
}

export const taskDataKeys = {
  byTaskId: (taskId: string) => ['task-data', taskId] as const,
};
