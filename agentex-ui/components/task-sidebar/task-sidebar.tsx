import { useCallback, useState } from 'react';

import { MessageSquarePlus, PanelLeftOpen } from 'lucide-react';

import { IconButton } from '@/components/agentex/icon-button';
import { ResizableSidebar } from '@/components/agentex/resizable-sidebar';
import { Separator } from '@/components/ui/separator';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

import { TaskSidebarBody } from './task-sidebar-body';
import { TaskSidebarFooter } from './task-sidebar-footer';
import { TaskSidebarHeader } from './task-sidebar-header';

export function TaskSidebar() {
  const { updateParams } = useSafeSearchParams();
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);

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
      className="flex h-full flex-col gap-2 pt-4"
      isCollapsed={isCollapsed}
      renderCollapsed={() => (
        <div className="flex flex-col items-center gap-4">
          <IconButton
            icon={PanelLeftOpen}
            onClick={toggleCollapse}
            variant="ghost"
            className="text-foreground"
            aria-label="Open Task Sidebar"
          />
          <IconButton
            icon={MessageSquarePlus}
            onClick={handleNewChat}
            variant="ghost"
            className="text-foreground"
            aria-label="New Chat"
          />
        </div>
      )}
    >
      <TaskSidebarHeader
        toggleCollapse={toggleCollapse}
        handleNewChat={handleNewChat}
      />
      <Separator />
      <TaskSidebarBody className="flex-1" />
      <TaskSidebarFooter />
    </ResizableSidebar>
  );
}
