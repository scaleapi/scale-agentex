import { useCallback } from 'react';

import { MessageSquare } from 'lucide-react';

import { cn } from '@/lib/utils';

import { ResizableSidebar } from '../agentex/resizable-sidebar';

export type TaskSidebarFooterProps = {
  className?: string;
};

export function TaskSidebarFooter({ className }: TaskSidebarFooterProps) {
  const handleFeedback = useCallback(() => {
    window.open(
      'https://github.com/scaleapi/scale-agentex/issues/new',
      '_blank',
      'noopener,noreferrer'
    );
  }, []);

  return (
    <div className={cn('mx-2 flex flex-col gap-2', className)}>
      <ResizableSidebar.Button
        onClick={handleFeedback}
        className="mb-2 p-3"
        disableAnimation
      >
        <MessageSquare className="size-5" />
        Give Feedback
      </ResizableSidebar.Button>
    </div>
  );
}
