import { memo, useCallback, useMemo } from 'react';

import { formatDistanceToNow } from 'date-fns';
import { motion } from 'framer-motion';

import { Button } from '@/components/ui/button';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import { cn } from '@/lib/utils';

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
    <motion.div
      className=""
      layout
      initial={{ opacity: 0, x: -50 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -50 }}
      transition={{
        layout: { duration: 0.3, ease: 'easeInOut' },
        opacity: {
          duration: 0.2,
          delay: 0.2,
        },
        x: {
          delay: 0.2,
          type: 'spring',
          damping: 30,
          stiffness: 300,
        },
      }}
    >
      <Button
        variant="ghost"
        className={`hover:bg-sidebar-accent hover:text-sidebar-primary-foreground flex h-auto w-full cursor-pointer flex-col items-start justify-start gap-1 px-2 py-2 text-left transition-colors ${
          taskID === task.id
            ? 'bg-sidebar-primary text-sidebar-primary-foreground'
            : 'text-sidebar-foreground'
        }`}
        onClick={() => handleTaskSelect(task.id)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            handleTaskSelect(task.id);
          }
        }}
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
      </Button>
    </motion.div>
  );
}

const TaskButton = memo(TaskButtonImpl);

function createTaskName(task: TaskListResponse.TaskListResponseItem): string {
  if (
    task?.params?.description &&
    typeof task.params.description === 'string'
  ) {
    return task.params.description;
  }

  return 'Unnamed task';
}

export { TaskButton };
