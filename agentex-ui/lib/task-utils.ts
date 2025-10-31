import type { TaskListResponse } from 'agentex/resources';

export function createTaskName(
  task: TaskListResponse.TaskListResponseItem
): string {
  if (
    task?.params?.description &&
    typeof task.params.description === 'string'
  ) {
    return task.params.description;
  }

  return 'Unnamed task';
}
