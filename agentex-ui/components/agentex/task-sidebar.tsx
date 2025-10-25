import { useCallback, useMemo, useState } from 'react';

import Image from 'next/image';
import { useRouter } from 'next/navigation';

import { formatDistanceToNow } from 'date-fns';
import { AnimatePresence, motion } from 'framer-motion';
import {
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
import { useTasks } from '@/hooks/use-tasks';
import { cn } from '@/lib/utils';

import type { Task } from 'agentex/resources';

type TaskButtonProps = {
  task: Task;
  selectedTaskID: Task['id'] | null;
  selectTask: (taskID: Task['id'] | null) => void;
};

function TaskButton({ task, selectedTaskID, selectTask }: TaskButtonProps) {
  const taskName = createTaskName(task);

  return (
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
      <span
        className={cn(
          'text-muted-foreground text-xs',
          task.created_at ? 'block' : 'invisible'
        )}
      >
        {task.created_at
          ? formatDistanceToNow(new Date(task.created_at), { addSuffix: true })
          : 'No date'}
      </span>
    </Button>
  );
}

export type TaskSidebarProps = {
  selectedTaskID: Task['id'] | null;
  selectedAgentName?: string;
  onSelectTask: (taskID: Task['id'] | null) => void;
};

export function TaskSidebar({
  selectedTaskID,
  selectedAgentName,
  onSelectTask,
}: TaskSidebarProps) {
  const { agentexClient } = useAgentexClient();
  const { data: tasks = [], isLoading: isLoadingTasks } = useTasks(
    agentexClient,
    selectedAgentName ? { agentName: selectedAgentName } : undefined
  );

  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);

  // Reverse tasks to show newest first
  const reversedTasks = useMemo(() => [...tasks].reverse(), [tasks]);

  const handleTaskSelect = useCallback(
    (taskID: Task['id'] | null) => {
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
      className="px-2 py-4"
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
        <div className="hide-scrollbar flex flex-col gap-1 overflow-y-auto">
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
            <AnimatePresence initial={false}>
              {reversedTasks.length > 0 &&
                reversedTasks.map(task => (
                  <motion.div
                    key={task.id}
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
                    <TaskButton
                      task={task}
                      selectedTaskID={selectedTaskID}
                      selectTask={handleTaskSelect}
                    />
                  </motion.div>
                ))}
            </AnimatePresence>
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
        className="text-sidebar-foreground flex items-center justify-start gap-2"
      >
        <SquarePen className="size-5" />
        New Chat
      </Button>
    </div>
  );
}

function createTaskName(task: Task): string {
  if (
    task?.params?.description &&
    typeof task.params.description === 'string'
  ) {
    return task.params.description;
  }

  return 'Unnamed task';
}
