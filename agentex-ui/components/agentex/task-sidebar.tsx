import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import Image from 'next/image';
import { useRouter } from 'next/navigation';

import { formatDistanceToNow } from 'date-fns';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Loader2,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  SquarePen,
} from 'lucide-react';

import { IconButton } from '@/components/agentex/icon-button';
import { ResizableSidebar } from '@/components/agentex/resizable-sidebar';
import { useAgentexClient } from '@/components/providers';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { useInfiniteTasks } from '@/hooks/use-tasks';
import { cn } from '@/lib/utils';

import type { TaskListResponse } from 'agentex/resources';

type TaskButtonProps = {
  task: TaskListResponse.TaskListResponseItem;
  selectedTaskID: TaskListResponse.TaskListResponseItem['id'] | null;
  selectTask: (
    taskID: TaskListResponse.TaskListResponseItem['id'] | null
  ) => void;
};

function TaskButton({ task, selectedTaskID, selectTask }: TaskButtonProps) {
  const taskName = createTaskName(task);
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
          selectedTaskID === task.id
            ? 'bg-sidebar-primary text-sidebar-primary-foreground'
            : 'text-sidebar-foreground'
        }`}
        onClick={() => selectTask(task.id)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            selectTask(task.id);
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

export type TaskSidebarProps = {
  selectedTaskID: TaskListResponse.TaskListResponseItem['id'] | null;
  selectedAgentName?: string;
  onSelectTask: (
    taskID: TaskListResponse.TaskListResponseItem['id'] | null
  ) => void;
};

export function TaskSidebar({
  selectedTaskID,
  selectedAgentName,
  onSelectTask,
}: TaskSidebarProps) {
  const { agentexClient } = useAgentexClient();

  const {
    data,
    isLoading: isLoadingTasks,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteTasks(
    agentexClient,
    selectedAgentName ? { agentName: selectedAgentName } : undefined
  );

  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Flatten all pages into a single array of tasks
  const tasks = useMemo(() => {
    return data?.pages.flatMap(page => page) ?? [];
  }, [data]);

  // Scroll detection for infinite loading
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
      // Trigger fetch when user is within 100px of the bottom
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;

      if (isNearBottom && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    };

    scrollContainer.addEventListener('scroll', handleScroll);
    return () => scrollContainer.removeEventListener('scroll', handleScroll);
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const handleTaskSelect = useCallback(
    (taskID: TaskListResponse.TaskListResponseItem['id'] | null) => {
      onSelectTask(taskID);
    },
    [onSelectTask]
  );

  const handleNewChat = useCallback(() => {
    onSelectTask(null);
  }, [onSelectTask]);

  const toggleCollapse = useCallback(() => {
    setIsCollapsed(prev => !prev);
  }, []);

  return (
    <ResizableSidebar
      side="left"
      storageKey="taskSidebarWidth"
      className="py-4"
      isCollapsed={isCollapsed}
      renderCollapsed={() => (
        <div className="flex flex-col items-center gap-4">
          <IconButton
            icon={PanelLeftOpen}
            onClick={toggleCollapse}
            variant="ghost"
            className="text-sidebar-foreground"
          />
          <IconButton
            icon={MessageSquarePlus}
            onClick={handleNewChat}
            variant="ghost"
            className="text-sidebar-foreground"
          />
        </div>
      )}
    >
      <div className="flex h-full flex-col gap-2">
        <SidebarHeader
          handleNewChat={handleNewChat}
          toggleCollapse={toggleCollapse}
        />
        <Separator />
        <div
          ref={scrollContainerRef}
          className="flex flex-col gap-1 overflow-y-auto px-2"
        >
          {isLoadingTasks ? (
            <>
              {[...Array(8)].map((_, i) => (
                <div className="flex flex-col gap-1 px-4 py-2 pl-2" key={i}>
                  <Skeleton className="h-5 w-full" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              ))}
            </>
          ) : (
            <>
              <AnimatePresence initial={false}>
                {tasks.length > 0 &&
                  tasks.map(task => (
                    <TaskButton
                      key={task.id}
                      task={task}
                      selectedTaskID={selectedTaskID}
                      selectTask={handleTaskSelect}
                    />
                  ))}
              </AnimatePresence>
              {isFetchingNextPage && (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="text-muted-foreground size-5 animate-spin" />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </ResizableSidebar>
  );
}

function SidebarHeader({
  handleNewChat,
  toggleCollapse,
}: {
  handleNewChat: () => void;
  toggleCollapse: () => void;
}) {
  const router = useRouter();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <Button variant="logo" onClick={() => router.push('/')}>
          <Image
            src="/scale-logo.svg"
            alt="Scale"
            className="text-sidebar-foreground dark:invert"
            width={60}
            height={20}
          />
        </Button>
        <IconButton
          icon={PanelLeftClose}
          onClick={toggleCollapse}
          variant="ghost"
          className="text-sidebar-foreground"
        />
      </div>
      <Button
        onClick={handleNewChat}
        variant="ghost"
        className="text-sidebar-foreground flex items-center justify-between gap-2"
      >
        <div className="flex items-center gap-2">
          <SquarePen className="size-5" />
          New Chat
        </div>
        <kbd className="bg-muted text-muted-foreground pointer-events-none inline-flex h-5 items-center gap-1 rounded border px-1.5 font-mono text-[10px] font-medium opacity-100 select-none">
          <span className="text-xs/snug">⌘</span>K
        </kbd>
      </Button>
    </div>
  );
}

function createTaskName(task: TaskListResponse.TaskListResponseItem): string {
  if (
    task?.params?.description &&
    typeof task.params.description === 'string'
  ) {
    return task.params.description;
  }

  return 'Unnamed task';
}
