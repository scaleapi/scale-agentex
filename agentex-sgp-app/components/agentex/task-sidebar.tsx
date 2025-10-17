import { Button } from '@/components/ui/button';
import { useAgentexRootStore } from '@/hooks/use-agentex-root-store';
import { useTaskName } from '@/hooks/use-task-name';
import type { Task, TaskMessage } from 'agentex/resources';
import { MessageSquare } from 'lucide-react';
import { useCallback, useMemo, useRef } from 'react';
import Image from 'next/image';
import useResizable from '../hooks/use-resizable';
import { useLocalStorageState } from '../hooks/use-local-storage-state';
import {
  MIN_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  DEFAULT_SIDEBAR_WIDTH,
} from '../ui/constants/sidebar';
import { useRouter } from 'next/navigation';

type TaskButtonProps = {
  task: Task;
  taskMessageCache: { taskID: Task['id']; messages: TaskMessage[] }[];
  selectedTaskID: Task['id'] | null;
  selectTask: (taskID: Task['id'] | null) => void;
};

function TaskButton({
  task,
  taskMessageCache,
  selectedTaskID,
  selectTask,
}: TaskButtonProps) {
  const cacheEntry = taskMessageCache.find((entry) => entry.taskID === task.id);
  const messages = cacheEntry?.messages;
  const taskName = useTaskName(task, messages);

  return (
    <Button
      variant="ghost"
      className={`flex cursor-pointer justify-start w-full text-left pl-2 py-1 transition-colors hover:bg-sidebar-accent hover:text-sidebar-primary-foreground ${
        selectedTaskID === task.id
          ? 'bg-sidebar-primary text-sidebar-primary-foreground'
          : 'text-sidebar-foreground'
      }`}
      onClick={() => selectTask(task.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          selectTask(task.id);
        }
      }}
    >
      <span className="truncate">{taskName}</span>
    </Button>
  );
}

export type TaskSidebarProps = {
  selectedTaskID: Task['id'] | null;
  onSelectTask: (taskID: Task['id'] | null) => void;
};

export function TaskSidebar({
  selectedTaskID,
  onSelectTask,
}: TaskSidebarProps) {
  const tasks = useAgentexRootStore((s) => s.tasks);
  const taskMessageCache = useAgentexRootStore((s) => s.taskMessageCache);
  const resizableContainerRef = useRef<HTMLDivElement>(null);
  const [secondarySidebarWidth, setSecondarySidebarWidth] =
    useLocalStorageState('sidebarWidth', DEFAULT_SIDEBAR_WIDTH);

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

  const {
    onMouseDown: handleStartResize,
    size,
    onDoubleClick: resetSidebarWidth,
  } = useResizable({
    ref: resizableContainerRef,
    initialSize: secondarySidebarWidth,
    minWidth: MIN_SIDEBAR_WIDTH,
    maxWidth: MAX_SIDEBAR_WIDTH,
    onResizeEnd: (newWidth) => {
      setSecondarySidebarWidth(newWidth);
    },
  });

  return (
    <div
      ref={resizableContainerRef}
      style={{ width: `${size}px` }}
      className="relative flex flex-col px-2 py-4 gap-2 border-r border-sidebar-border group"
    >
      <SidebarHeader handleNewChat={handleNewChat} />

      <hr className="bg-sidebar-border h-1 px-4" />

      <div className="flex flex-col overflow-y-auto gap-1 hide-scrollbar">
        {reversedTasks.length > 0 ? (
          reversedTasks.map((task) => (
            <TaskButton
              key={task.id}
              task={task}
              taskMessageCache={taskMessageCache}
              selectedTaskID={selectedTaskID}
              selectTask={handleTaskSelect}
            />
          ))
        ) : (
          <p className="text-sidebar-foreground text-sm">No tasks found.</p>
        )}
      </div>

      {/* Drag handle to resize the sidebar */}
      <div
        className="absolute right-[-2px] top-0 w-1 h-full hover:w-1 hover:bg-sidebar-accent transition-all duration-300"
        style={{
          cursor:
            size === MIN_SIDEBAR_WIDTH
              ? 'e-resize'
              : size === MAX_SIDEBAR_WIDTH
                ? 'w-resize'
                : 'col-resize',
        }}
        onMouseDown={handleStartResize}
        onDoubleClick={resetSidebarWidth}
      />
    </div>
  );
}
function SidebarHeader({ handleNewChat }: { handleNewChat: () => void }) {
  const router = useRouter();

  return (
    <div className="flex flex-col gap-4">
      <button
        className="flex pl-3 justify-start items-center"
        onClick={() => router.push('/')}
      >
        <Image
          src="/scale-logo.svg"
          alt="Scale"
          width={60}
          height={20}
          className="text-gray-800 dark:invert"
        />
      </button>

      <Button
        variant="ghost"
        className="group cursor-pointer justify-start w-full text-left text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-primary-foreground transition-colors"
        onClick={() => handleNewChat()}
      >
        <MessageSquare className="h-4 w-4 text-muted-foreground group-hover:text-sidebar-primary-foreground" />
        New chat
      </Button>
    </div>
  );
}
