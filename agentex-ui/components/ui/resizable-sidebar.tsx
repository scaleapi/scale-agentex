'use client';

import { useRef, useState } from 'react';

import { motion, AnimatePresence } from 'framer-motion';

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

export function ResizableSidebar({
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
    <AnimatePresence mode="wait">
      <motion.div
        ref={resizableContainerRef}
        key={`resizable-sidebar-${storageKey}`}
        className={cn(
          'relative flex h-full flex-col',
          borderClass,
          'border-border group overflow-hidden',
          className
        )}
        initial={false}
        animate={{
          width: animatedWidth,
        }}
        suppressHydrationWarning
        transition={
          isManuallyResizing
            ? { duration: 0 }
            : {
                width: {
                  type: 'spring',
                  damping: 30,
                  stiffness: 300,
                  duration: 0.3,
                },
              }
        }
      >
        <motion.div
          className="flex h-full flex-col"
          animate={{ opacity: contentOpacity }}
          transition={
            isManuallyResizing
              ? { duration: 0 }
              : {
                  duration: 0.15,
                  ease: 'easeInOut',
                  delay: isCollapsed ? 0 : 0.1,
                }
          }
        >
          <AnimatePresence mode="wait">
            {isCollapsed ? (
              <motion.div
                key={`collapsed-${storageKey}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex h-full flex-col"
              >
                {renderCollapsed ? (
                  renderCollapsed()
                ) : (
                  <div className="h-full w-full" />
                )}
              </motion.div>
            ) : (
              <motion.div
                key={`expanded-${storageKey}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex h-full flex-col"
              >
                {children}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
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
    </AnimatePresence>
  );
}
