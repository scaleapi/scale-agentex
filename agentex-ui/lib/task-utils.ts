import type { TaskListResponse } from 'agentex/resources';

const LEGACY_SCHEDULED_MESSAGE_PREFIX = 'Scheduled Message: ';

export function isScheduledTask(
  task: TaskListResponse.TaskListResponseItem
): boolean {
  const scheduleId = task?.task_metadata?.schedule_id;
  return typeof scheduleId === 'string' && scheduleId.length > 0;
}

/**
 * Derives the task_metadata.display_name written at task creation from the
 * user's prompt. This is the writer-side counterpart of createTaskName, which
 * reads display_name first — do not write the prompt into task.name, which is
 * a globally-unique get-or-create idempotency key, not a label.
 */
export function deriveTaskDisplayName(prompt: string): string {
  // Truncate by code points, not UTF-16 units: a unit-based slice can split a
  // surrogate pair, and Postgres rejects lone surrogates in JSONB, failing the
  // whole task/create request.
  return Array.from(prompt.trim().replace(/\s+/g, ' ')).slice(0, 80).join('');
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

  if (typeof task?.name === 'string' && task.name) {
    return task.name;
  }

  return 'Unnamed task';
}
