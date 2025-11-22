import { useCallback, useRef } from 'react';

import { motion } from 'framer-motion';

import { TaskProvider, useAgentexClient } from '@/components/providers';
import { TaskMessages } from '@/components/task-messages/task-messages';
import { useAgents } from '@/hooks/use-agents';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

import { TaskHeader } from '../task-header/task-header';

type ChatViewProps = {
  taskID: string;
  isTracesSidebarOpen: boolean;
  toggleTracesSidebar: () => void;
  setPrompt: (prompt: string) => void;
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
};

export function ChatView({
  taskID,
  isTracesSidebarOpen,
  toggleTracesSidebar,
  setPrompt,
  scrollContainerRef,
}: ChatViewProps) {
  const { agentexClient } = useAgentexClient();
  const { data: agents = [] } = useAgents(agentexClient);
  const { updateParams } = useSafeSearchParams();

  const headerRef = useRef<HTMLDivElement>(null);

  const handleSelectAgent = useCallback(
    (agentName: string | undefined) => {
      updateParams({
        [SearchParamKey.AGENT_NAME]: agentName ?? null,
        [SearchParamKey.TASK_ID]: null,
      });
      setPrompt('');
    },
    [updateParams, setPrompt]
  );

  return (
    <motion.div
      key="chat-view"
      layout
      ref={scrollContainerRef}
      className="relative flex-1 flex-col overflow-y-auto"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
    >
      <TaskHeader
        taskId={taskID}
        isTracesSidebarOpen={isTracesSidebarOpen}
        toggleTracesSidebar={toggleTracesSidebar}
        agents={agents}
        onAgentChange={handleSelectAgent}
        ref={headerRef}
      />

      <div className="flex w-full flex-col items-center px-4 sm:px-6 md:px-8">
        <div className="w-full max-w-3xl">
          <TaskProvider taskId={taskID}>
            <TaskMessages taskId={taskID} headerRef={headerRef} />
          </TaskProvider>
        </div>
      </div>
    </motion.div>
  );
}
