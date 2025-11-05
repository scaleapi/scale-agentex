import { useCallback } from 'react';

import { MessageSquare } from 'lucide-react';

import { Separator } from '@/components/ui/separator';
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
    <div className={cn('flex flex-col gap-2', className)}>
      <Separator />
      <div className="mx-2">
        <ResizableSidebar.Button onClick={handleFeedback} className="mb-2 p-3">
          <MessageSquare className="size-5" />
          Give Feedback
        </ResizableSidebar.Button>
      </div>
    </div>
  );
}
