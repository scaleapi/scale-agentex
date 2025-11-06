import { useRef } from 'react';

import { motion } from 'framer-motion';

import { TaskProvider } from '@/components/providers';
import { TaskMessages } from '@/components/task-messages/task-messages';

export function ChatView({ taskID }: { taskID: string }) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  return (
    <motion.div
      key="chat-view"
      layout
      ref={scrollContainerRef}
      className="relative flex-1 overflow-y-auto"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
    >
      <div className="flex min-h-full w-full flex-col items-center px-4 sm:px-6 md:px-8">
        <div className="w-full max-w-3xl">
          <TaskProvider taskId={taskID}>
            <TaskMessages taskId={taskID} />
          </TaskProvider>
        </div>
      </div>
    </motion.div>
  );
}
