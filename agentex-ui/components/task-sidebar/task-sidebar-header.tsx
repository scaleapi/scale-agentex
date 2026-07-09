import Image from 'next/image';
import { useRouter } from 'next/navigation';

import { CalendarClock, PanelLeftClose, MessageSquarePlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  AppView,
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import { cn } from '@/lib/utils';

import { IconButton } from '../ui/icon-button';
import { ResizableSidebar } from '../ui/resizable-sidebar';

export type TaskSidebarHeaderProps = {
  toggleCollapse: () => void;
  handleNewChat: () => void;
  className?: string;
};

export function TaskSidebarHeader({
  toggleCollapse,
  handleNewChat,
  className,
}: TaskSidebarHeaderProps) {
  const router = useRouter();
  const { view, updateParams } = useSafeSearchParams();

  const handleScheduledTasks = () => {
    updateParams({
      [SearchParamKey.TASK_ID]: null,
      [SearchParamKey.VIEW]: AppView.SCHEDULED_TASKS,
    });
  };

  return (
    <div className={cn('flex flex-col gap-4 px-2', className)}>
      <div className="flex items-center justify-between">
        <Button variant="logo" onClick={() => router.push('/')} className="p-2">
          <Image
            src="/scale-logo.svg"
            alt="Scale"
            className="text-foreground dark:invert"
            width={60}
            height={20}
          />
        </Button>
        <IconButton
          icon={PanelLeftClose}
          onClick={toggleCollapse}
          variant="ghost"
          className="text-foreground"
          aria-label="Close Task Sidebar"
        />
      </div>
      <ResizableSidebar.Button
        onClick={handleNewChat}
        className="text-foreground flex items-center justify-between gap-2 p-2"
        aria-label="New Chat"
        disableAnimation={true}
      >
        <div className="flex items-center gap-2">
          <MessageSquarePlus className="size-5" />
          New Chat
        </div>
        <kbd className="bg-muted text-muted-foreground pointer-events-none inline-flex h-5 items-center gap-1 rounded border px-1.5 font-mono text-[10px] font-medium opacity-100 select-none">
          <span className="text-xs/snug">⌘</span>K
        </kbd>
      </ResizableSidebar.Button>
      <ResizableSidebar.Button
        onClick={handleScheduledTasks}
        isSelected={view === AppView.SCHEDULED_TASKS}
        className="text-foreground flex items-center gap-2 p-2"
        aria-label="Scheduled Tasks"
        disableAnimation={true}
      >
        <CalendarClock className="size-5" />
        Scheduled Tasks
      </ResizableSidebar.Button>
    </div>
  );
}
