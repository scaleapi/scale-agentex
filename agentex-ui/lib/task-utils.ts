import type { TaskListResponse } from 'agentex/resources';

const LEGACY_SCHEDULED_MESSAGE_PREFIX = 'Scheduled Message: ';

export function isScheduledTask(
  task: TaskListResponse.TaskListResponseItem
): boolean {
  const scheduleId = task?.task_metadata?.schedule_id;
  return typeof scheduleId === 'string' && scheduleId.length > 0;
}

export function createTaskName(
  task: TaskListResponse.TaskListResponseItem
): string {
  const displayName = task?.task_metadata?.display_name;
  if (typeof displayName === 'string' && displayName) {
    if (isScheduledTask(task)) {
      return displayName.replace(LEGACY_SCHEDULED_MESSAGE_PREFIX, '');
    }
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
