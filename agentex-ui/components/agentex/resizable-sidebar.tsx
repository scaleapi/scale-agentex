'use client';

import { useRef, useState } from 'react';

import { motion, AnimatePresence } from 'framer-motion';

import { Button } from '@/components/ui/button';
import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import useResizable from '@/hooks/use-resizable';
import { cn } from '@/lib/utils';

export const DEFAULT_SIDEBAR_WIDTH = 150;
export const MIN_SIDEBAR_WIDTH = 120;
export const MAX_SIDEBAR_WIDTH = 500;
export const DEFAULT_COLLAPSED_WIDTH = 60;

type ResizableSidebarProps = React.HTMLAttributes<HTMLDivElement> & {
  side: 'left' | 'right';
  storageKey: string;
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  isCollapsed?: boolean;
  collapsedWidth?: number;
  renderCollapsed?: () => React.ReactNode;
};

type ResizableSidebarButtonProps = {
  onClick: () => void;
  isSelected?: boolean;
  className?: string;
  children: React.ReactNode;
  ariaLabel?: string;
  disableAnimation?: boolean;
};

type ResizableSidebarComponent = {
  (props: ResizableSidebarProps): React.ReactElement;
  Button: (props: ResizableSidebarButtonProps) => React.ReactElement;
};

function ResizableSidebarBase({
  children,
  side,
  storageKey,
  defaultWidth = DEFAULT_SIDEBAR_WIDTH,
  minWidth = MIN_SIDEBAR_WIDTH,
  maxWidth = MAX_SIDEBAR_WIDTH,
  className,
  isCollapsed = false,
  collapsedWidth = DEFAULT_COLLAPSED_WIDTH,
  renderCollapsed,
}: ResizableSidebarProps) {
  const resizableContainerRef = useRef<HTMLDivElement>(null);
  const [sidebarWidth, setSidebarWidth] = useLocalStorageState(
    storageKey,
    defaultWidth
  );
  const [isManuallyResizing, setIsManuallyResizing] = useState(false);

  const {
    onMouseDown: handleStartResize,
    size,
    onDoubleClick: resetSidebarWidth,
  } = useResizable({
    ref: resizableContainerRef,
    initialSize: sidebarWidth,
    minWidth,
    maxWidth,
    invertDragDirection: side === 'right',
    onResizeStart: () => {
      setIsManuallyResizing(true);
    },
    onResizeEnd: newWidth => {
      setSidebarWidth(newWidth);
      setTimeout(() => {
        setIsManuallyResizing(false);
      }, 50);
    },
  });

  const isLeftSide = side === 'left';
  const dragHandlePosition = isLeftSide ? 'right-[-2px]' : 'left-[-2px]';
  const borderClass = isLeftSide ? 'border-r' : 'border-l';

  const animatedWidth = isCollapsed ? collapsedWidth : sidebarWidth;
  const shouldFadeContent = !isManuallyResizing && collapsedWidth === 0;
  const contentOpacity = shouldFadeContent && isCollapsed ? 0 : 1;

  return (
    <motion.div
      ref={resizableContainerRef}
      className={cn(
        'relative flex h-full flex-col',
        borderClass,
        'border-border group overflow-hidden'
      )}
      initial={false}
      animate={{ width: animatedWidth, opacity: contentOpacity }}
      suppressHydrationWarning
      transition={{
        width: isManuallyResizing
          ? { duration: 0 }
          : { type: 'spring', damping: 30, stiffness: 200 },
        opacity: isManuallyResizing
          ? { duration: 0 }
          : {
              duration: 0.15,
              ease: 'easeInOut' as const,
            },
      }}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={isCollapsed ? 'collapsed' : 'expanded'}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className={cn('flex h-full flex-col', className)}
        >
          {isCollapsed
            ? (renderCollapsed?.() ?? <div className="h-full w-full" />)
            : children}
        </motion.div>
      </AnimatePresence>
      {!isCollapsed && (
        <div
          className={cn(
            'hover:bg-accent absolute top-0 h-full w-1 transition-all duration-300 hover:w-1',
            dragHandlePosition
          )}
          style={{
            cursor:
              size === minWidth
                ? isLeftSide
                  ? 'e-resize'
                  : 'w-resize'
                : size === maxWidth
                  ? isLeftSide
                    ? 'w-resize'
                    : 'e-resize'
                  : 'col-resize',
          }}
          onMouseDown={handleStartResize}
          onDoubleClick={resetSidebarWidth}
        />
      )}
    </motion.div>
  );
}

function ResizableSidebarButton({
  onClick,
  isSelected = false,
  className,
  children,
  ariaLabel,
  disableAnimation = false,
}: ResizableSidebarButtonProps) {
  if (disableAnimation) {
    return (
      <Button
        variant="ghost"
        className={cn(
          'hover:bg-muted hover:text-primary-foreground text-foreground flex h-auto w-full cursor-pointer items-start justify-start p-2 text-left transition-colors active:opacity-80',
          isSelected && 'bg-primary',
          className
        )}
        onClick={onClick}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick();
          }
        }}
        aria-label={ariaLabel}
      >
        {children}
      </Button>
    );
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -50 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -50 }}
      whileTap={{ scale: 0.98 }}
      transition={{
        layout: { duration: 0.3, ease: 'easeInOut' },
        opacity: { duration: 0.2, delay: 0.2 },
        x: { delay: 0.2, type: 'spring', damping: 30, stiffness: 300 },
      }}
    >
      <Button
        variant="ghost"
        className={cn(
          'hover:bg-muted hover:text-primary-foreground text-foreground flex h-auto w-full cursor-pointer items-start justify-start p-2 text-left transition-colors active:opacity-80',
          isSelected && 'bg-primary',
          className
        )}
        onClick={onClick}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick();
          }
        }}
        aria-label={ariaLabel}
      >
        {children}
      </Button>
    </motion.div>
  );
}

// Create compound component
const ResizableSidebar = ResizableSidebarBase as ResizableSidebarComponent;
ResizableSidebar.Button = ResizableSidebarButton;

export { ResizableSidebar };
