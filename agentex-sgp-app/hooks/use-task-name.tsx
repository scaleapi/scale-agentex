import type { Task, TaskMessage } from 'agentex/resources';
import { formatDistanceToNow } from 'date-fns';
import { useEffect, useState } from 'react';

function createTaskNameDerivedFromTaskMessages(
  taskMessages: TaskMessage[] | undefined
): string | null {
  const [cleanFirstMessageContent] =
    taskMessages?.flatMap((m): string[] => {
      const { content } = m;
      const { author } = content;
      if (author !== 'user' || content.type !== 'text') {
        return [];
      }

      const cleanContent = content.content.replace(/\s+/g, ' ').trim();
      if (!cleanContent) {
        return [];
      }

      return [cleanContent];
    }) ?? [];

  if (cleanFirstMessageContent === undefined) {
    return null;
  }

  const desiredTaskNameLength = 64;
  const ellipsis = '...';
  if (cleanFirstMessageContent.length > desiredTaskNameLength) {
    return (
      cleanFirstMessageContent.slice(
        0,
        desiredTaskNameLength - ellipsis.length
      ) + ellipsis
    );
  }

  return cleanFirstMessageContent;
}

function createTaskName(
  task: Task | undefined,
  taskMessages: TaskMessage[] | undefined
): string {
  const cleanTaskName = task?.name?.replaceAll(/\s+/g, ' ').trim();
  if (cleanTaskName) {
    return cleanTaskName;
  }

  const derivedFromMessages =
    createTaskNameDerivedFromTaskMessages(taskMessages);
  if (derivedFromMessages) {
    return derivedFromMessages;
  }

  const unnamedTask = 'Unnamed task';
  if (task?.created_at) {
    return (
      unnamedTask +
      ' from ' +
      formatDistanceToNow(task.created_at, {
        addSuffix: true,
        includeSeconds: false,
      })
    );
  }

  return unnamedTask;
}

export function useTaskName(
  task: Task | undefined,
  taskMessages: TaskMessage[] | undefined
): string {
  const [name, setName] = useState(() => createTaskName(task, taskMessages));

  useEffect(() => {
    setName(createTaskName(task, taskMessages));

    const interval = setInterval(() => {
      setName(createTaskName(task, taskMessages));
    }, 60_000);

    return () => clearInterval(interval);
  }, [task, taskMessages, setName]);

  return name;
}
