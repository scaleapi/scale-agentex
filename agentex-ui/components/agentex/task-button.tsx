import { memo, useCallback, useMemo } from 'react';

import { formatDistanceToNow } from 'date-fns';

import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import { createTaskName } from '@/lib/task-utils';
import { cn } from '@/lib/utils';

import { ResizableSidebar } from './resizable-sidebar';

import type { TaskListResponse } from 'agentex/resources';

type TaskButtonProps = {
  task: TaskListResponse.TaskListResponseItem;
};

function TaskButtonImpl({ task }: TaskButtonProps) {
  const { taskID, updateParams } = useSafeSearchParams();
  const taskName = createTaskName(task);

  const firstAgentName = useMemo(
    () => task.agents?.[0]?.name ?? null,
    [task.agents]
  );

  const handleTaskSelect = useCallback(
    (taskID: TaskListResponse.TaskListResponseItem['id']) => {
      updateParams({
        [SearchParamKey.TASK_ID]: taskID,
        [SearchParamKey.AGENT_NAME]: firstAgentName,
      });
    },
    [updateParams, firstAgentName]
  );

  const createdAtString = useMemo(
    () =>
      task.created_at
        ? formatDistanceToNow(new Date(task.created_at), {
            addSuffix: true,
          })
        : 'No date',
    [task.created_at]
  );
  const agentsString = useMemo(() => {
    if (!task.agents || task.agents.length === 0) return 'No agents';

    const firstAgent = task.agents[0];
    if (!firstAgent) return 'No agents';

    if (task.agents.length === 1) {
      return firstAgent.name;
    }

    return `${firstAgent.name} + ${task.agents.length - 1} more`;
  }, [task.agents]);

  return (
    <ResizableSidebar.Button
      onClick={() => handleTaskSelect(task.id)}
      isSelected={taskID === task.id}
      className={cn('flex flex-col gap-1 text-left')}
    >
      <span className="w-full truncate text-sm">{taskName}</span>
      <div
        className={cn(
          'text-muted-foreground w-full truncate text-xs',
          (task.agents && task.agents.length > 0) || task.created_at
            ? 'block'
            : 'invisible'
        )}
      >
        {createdAtString}
        {task.agents && task.agents.length > 0 && task.created_at && ' • '}
        {agentsString}
      </div>
    </ResizableSidebar.Button>
  );
}

const TaskButton = memo(TaskButtonImpl);

export { TaskButton };
