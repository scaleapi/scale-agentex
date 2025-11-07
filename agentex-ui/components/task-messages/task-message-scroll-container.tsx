import type { ReactNode } from 'react';
import { forwardRef } from 'react';

import { cn } from '@/lib/utils';

type TaskMessageScrollContainerProps = {
  isLastPair: boolean;
  containerHeight: number;
  children: ReactNode;
  className?: string;
};

const TaskMessageScrollContainer = forwardRef<
  HTMLDivElement,
  TaskMessageScrollContainerProps
>(({ isLastPair, containerHeight, children, className }, ref) => {
  return (
    <div
      ref={ref}
      className={cn('flex w-full flex-col gap-4 px-4 pt-4', className)}
      style={
        isLastPair && containerHeight > 0
          ? {
              minHeight: `${containerHeight}px`,
            }
          : {}
      }
    >
      {children}
    </div>
  );
});

TaskMessageScrollContainer.displayName = 'TaskMessageScrollContainer';

export { TaskMessageScrollContainer };
