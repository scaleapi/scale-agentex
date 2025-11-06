import { useEffect, useMemo, useRef } from 'react';

import { AnimatePresence } from 'framer-motion';
import { Loader2 } from 'lucide-react';

import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useInfiniteTasks } from '@/hooks/use-tasks';
import { cn } from '@/lib/utils';

import { TaskButton } from './task-button';
import { useAgentexClient } from '../providers';
import { Skeleton } from '../ui/skeleton';

export type TaskSidebarBodyProps = {
  className?: string;
};

export const TaskSidebarBody = ({ className }: TaskSidebarBodyProps) => {
  const { agentexClient } = useAgentexClient();
  const { agentName } = useSafeSearchParams();
  const scrollContainerRef = useRef<HTMLDivElement>(null);

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

  const tasks = useMemo(() => {
    return data?.pages?.flatMap(page => page) ?? [];
  }, [data]);

  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;

      if (isNearBottom && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    };

    scrollContainer.addEventListener('scroll', handleScroll);
    return () => scrollContainer.removeEventListener('scroll', handleScroll);
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const bodyClassName = cn(
    'flex flex-col gap-1 overflow-y-auto px-2',
    className
  );

  if (isLoadingTasks) {
    return (
      <div className={bodyClassName}>
        {[...Array(8)].map((_, i) => (
          <Skeleton className="h-5 w-full" key={i} />
        ))}
      </div>
    );
  }

  return (
    <div ref={scrollContainerRef} className={bodyClassName}>
      <AnimatePresence initial={false}>
        {tasks.length > 0 &&
          tasks.map(task => <TaskButton key={task.id} task={task} />)}
      </AnimatePresence>
      {isFetchingNextPage && (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="text-muted-foreground size-5 animate-spin" />
        </div>
      )}
    </div>
  );
};
