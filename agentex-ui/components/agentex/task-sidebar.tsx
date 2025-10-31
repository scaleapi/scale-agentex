import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import Image from 'next/image';
import { useRouter } from 'next/navigation';

import { AnimatePresence } from 'framer-motion';
import {
  Loader2,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  SquarePen,
} from 'lucide-react';

import { IconButton } from '@/components/agentex/icon-button';
import { ResizableSidebar } from '@/components/agentex/resizable-sidebar';
import { TaskButton } from '@/components/agentex/task-button';
import { useAgentexClient } from '@/components/providers';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import { useInfiniteTasks } from '@/hooks/use-tasks';

export function TaskSidebar() {
  const { agentName, updateParams } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();

  const {
    data,
    isLoading: isLoadingTasks,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteTasks(
    agentexClient,
    agentName ? { agentName: agentName } : undefined
  );

  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const tasks = useMemo(() => {
    return data?.pages?.flatMap(page => page) ?? [];
  }, [data]);

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

  const handleNewChat = useCallback(() => {
    updateParams({
      [SearchParamKey.TASK_ID]: null,
    });
  }, [updateParams]);

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
                  tasks.map(task => <TaskButton key={task.id} task={task} />)}
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
