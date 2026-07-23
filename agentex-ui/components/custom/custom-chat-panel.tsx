'use client';

import { useRef } from 'react';

import { motion } from 'framer-motion';

import { useAgentexClient } from '@/components/providers';
import { TaskMessages } from '@/components/task-messages/task-messages';
import { CopyButton } from '@/components/ui/copy-button';
import { useTaskSubscription } from '@/hooks/use-task-subscription';

const GOLDEN_AGENT_NAME = 'golden-agent';

type CustomChatPanelProps = {
  taskId: string | null;
};

export function CustomChatPanel({ taskId }: CustomChatPanelProps) {
  const { agentexClient } = useAgentexClient();
  const headerRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useTaskSubscription({
    agentexClient,
    taskId: taskId ?? '',
    agentName: GOLDEN_AGENT_NAME,
    enabled: !!taskId,
  });

  if (!taskId) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-muted-foreground text-sm">
          Configure the agent and send a message to start.
        </p>
      </div>
    );
  }

  return (
    <motion.div
      key={taskId}
      ref={scrollContainerRef}
      className="relative flex-1 flex-col overflow-x-hidden overflow-y-auto"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
    >
      <div
        ref={headerRef}
        className="bg-background/80 sticky top-0 z-10 flex items-center gap-2 border-b px-4 py-2 backdrop-blur-sm"
      >
        <span className="text-muted-foreground text-xs font-medium">
          golden-agent
        </span>
        <span className="text-muted-foreground text-xs">|</span>
        <span className="text-muted-foreground font-mono text-xs">
          {taskId.slice(0, 8)}...
        </span>
        <CopyButton content={taskId} tooltip="Copy task ID" />
      </div>

      <div className="flex w-full flex-col items-center px-4 sm:px-6 md:px-8">
        <div className="w-full max-w-3xl">
          <TaskMessages
            taskId={taskId}
            headerRef={headerRef}
            scrollContainerRef={scrollContainerRef}
            agentNameOverride={GOLDEN_AGENT_NAME}
          />
        </div>
      </div>
    </motion.div>
  );
}
