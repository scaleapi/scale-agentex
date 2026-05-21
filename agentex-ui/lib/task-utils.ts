import type { TaskListResponse } from 'agentex/resources';

export function createTaskName(
  task: TaskListResponse.TaskListResponseItem
): string {
  const displayName = task?.task_metadata?.display_name;
  if (typeof displayName === 'string' && displayName) {
    return displayName;
  }

  if (
    task?.params?.description &&
    typeof task.params.description === 'string'
  ) {
    return task.params.description;
  }

  return 'Unnamed task';
}
