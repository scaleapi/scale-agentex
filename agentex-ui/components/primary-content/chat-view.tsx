import { useCallback, useEffect, useRef } from 'react';

import { APIError } from 'agentex';
import { motion } from 'framer-motion';

import { TaskProvider, useAgentexClient } from '@/components/providers';
import { TaskMessages } from '@/components/task-messages/task-messages';
import { useAgents } from '@/hooks/use-agents';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import { useTask } from '@/hooks/use-tasks';

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
  const { agentName, updateParams } = useSafeSearchParams();
  const {
    data: task,
    isError: isTaskError,
    error: taskError,
  } = useTask({ agentexClient, taskId: taskID });

  const headerRef = useRef<HTMLDivElement>(null);

  // Deep links may carry only task_id — fill the agent pill from the task's own agent.
  const taskAgentName = task?.agents?.[0]?.name;
  useEffect(() => {
    if (agentName || !taskAgentName) return;
    updateParams({ [SearchParamKey.AGENT_NAME]: taskAgentName }, true);
  }, [agentName, taskAgentName, updateParams]);

  // Drop a task_id the client can't use: a 4xx means it's bad/off-limits (400/403/404/422).
  // 401 is handled by the session refresh + login redirect, and 429/5xx are transient.
  useEffect(() => {
    const status = taskError instanceof APIError ? taskError.status : undefined;
    if (
      isTaskError &&
      status !== undefined &&
      status >= 400 &&
      status < 500 &&
      status !== 401 &&
      status !== 429
    ) {
      updateParams(
        { [SearchParamKey.TASK_ID]: null, [SearchParamKey.AGENT_NAME]: null },
        true
      );
    }
  }, [isTaskError, taskError, updateParams]);

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
      className="relative flex-1 flex-col overflow-x-hidden overflow-y-auto"
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
            <TaskMessages
              taskId={taskID}
              headerRef={headerRef}
              scrollContainerRef={scrollContainerRef}
            />
          </TaskProvider>
        </div>
      </div>
    </motion.div>
  );
}
