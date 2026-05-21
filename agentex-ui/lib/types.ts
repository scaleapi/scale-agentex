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
  TERMINATED = 'TERMINATED',
  TIMED_OUT = 'TIMED_OUT',
  DELETED = 'DELETED',
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
