import { MessageSquare } from 'lucide-react';

import { IconButton } from '@/components/ui/icon-button';
import { ResizableSidebar } from '@/components/ui/resizable-sidebar';
import { cn } from '@/lib/utils';

const FEEDBACK_URL = 'https://github.com/scaleapi/scale-agentex/issues/new';

function openFeedback() {
  window.open(FEEDBACK_URL, '_blank', 'noopener,noreferrer');
}

export type TaskSidebarFooterProps = {
  className?: string;
  collapsed?: boolean;
};

export function TaskSidebarFooter({
  className,
  collapsed = false,
}: TaskSidebarFooterProps) {
  if (collapsed) {
    return (
      <div className={cn('flex flex-col items-start gap-2 pl-2', className)}>
        <IconButton
          icon={MessageSquare}
          onClick={openFeedback}
          variant="ghost"
          className="text-foreground"
          aria-label="Give Feedback"
        />
      </div>
    );
  }

  return (
    <div className={cn('mx-2 mb-2 flex flex-col gap-2', className)}>
      <ResizableSidebar.Button
        onClick={openFeedback}
        className="flex items-center gap-2 p-2"
        disableAnimation
      >
        <div className="flex items-center gap-2">
          <MessageSquare className="size-5" />
          Give Feedback
        </div>
      </ResizableSidebar.Button>
    </div>
  );
}
