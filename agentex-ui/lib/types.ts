import { Task } from 'agentex/resources';

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type TaskStatus = NonNullable<Task['status']>;

export enum TaskStatusEnum {
  CANCELED = 'CANCELED',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  RUNNING = 'RUNNING',
  INTERRUPTED = 'INTERRUPTED',
  TERMINATED = 'TERMINATED',
  TIMED_OUT = 'TIMED_OUT',
  DELETED = 'DELETED',
}

// Non-terminal statuses: the task is still continuable, so the composer stays
// enabled. INTERRUPTED is a resting state ("stopped by user, waiting for the
// next message") and must not be treated as terminal.
const NON_TERMINAL_TASK_STATUSES: ReadonlySet<string> = new Set([
  TaskStatusEnum.RUNNING,
  TaskStatusEnum.INTERRUPTED,
]);

export function isTaskTerminalStatus(
  status: string | null | undefined
): boolean {
  if (status == null) return false;
  return !NON_TERMINAL_TASK_STATUSES.has(status);
}

// API to frontend type checks
export const _taskStatusEnumCheck: Record<TaskStatus, true> = {
  [TaskStatusEnum.CANCELED]: true,
  [TaskStatusEnum.COMPLETED]: true,
  [TaskStatusEnum.FAILED]: true,
  [TaskStatusEnum.RUNNING]: true,
  [TaskStatusEnum.TERMINATED]: true,
  [TaskStatusEnum.TIMED_OUT]: true,
  [TaskStatusEnum.DELETED]: true,
};
