'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDown } from 'lucide-react';
import { ToastContainer } from 'react-toastify';

import { AgentsList } from '@/components/agentex/agents-list';
import { IconButton } from '@/components/agentex/icon-button';
import { PromptInput } from '@/components/agentex/prompt-input';
import { MemoizedTaskMessagesComponent } from '@/components/agentex/task-messages';
import { TaskSidebar } from '@/components/agentex/task-sidebar';
import { TaskTopBar } from '@/components/agentex/task-top-bar';
import { TracesSidebar } from '@/components/agentex/traces-sidebar';
import {
  AgentexProvider,
  TaskProvider,
  useAgentexClient,
} from '@/components/providers';
import { QueryProvider } from '@/components/providers/query-provider';
import { useAgents } from '@/hooks/use-agents';
import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

function NoAgentImpl() {
  const { taskID, agentName, updateParams } = useSafeSearchParams();
  const [isTracesSidebarOpen, setIsTracesSidebarOpen] = useState(false);
  const [localAgentName] = useLocalStorageState<string | undefined>(
    'lastSelectedAgent',
    undefined
  );

  const selectedAgentName = agentName ?? localAgentName;

  const handleSelectTask = useCallback(
    (taskId: string | null) => {
      updateParams({
        [SearchParamKey.TASK_ID]: taskId,
      });
    },
    [updateParams]
  );

  return (
    <div className="fixed inset-0 flex w-full">
      <AnimatePresence>
        {
          <motion.div
            key="task-sidebar"
            initial={{ opacity: 0, x: -20, width: 0 }}
            animate={{ opacity: 1, x: 0, width: 'auto' }}
            exit={{ opacity: 0, x: -20, width: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
          >
            <TaskSidebar
              selectedTaskID={taskID}
              selectedAgentName={selectedAgentName ?? ''}
              onSelectTask={handleSelectTask}
            />
          </motion.div>
        }
      </AnimatePresence>
      <ContentArea
        taskID={taskID}
        isTracesSidebarOpen={isTracesSidebarOpen}
        toggleTracesSidebar={() => setIsTracesSidebarOpen(!isTracesSidebarOpen)}
      />
      <AnimatePresence>
        {taskID && (
          <motion.div
            key="traces-sidebar"
            initial={{ opacity: 0, x: 20, width: 0 }}
            animate={{ opacity: 1, x: 0, width: 'auto' }}
            exit={{ opacity: 0, x: 20, width: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
          >
            <TracesSidebar isOpen={isTracesSidebarOpen} taskId={taskID} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface ContentAreaProps {
  taskID: string | null;
  isTracesSidebarOpen: boolean;
  toggleTracesSidebar: () => void;
}

function ContentArea({
  taskID,
  isTracesSidebarOpen,
  toggleTracesSidebar,
}: ContentAreaProps) {
  const { agentexClient } = useAgentexClient();
  const { data: agents = [], isLoading } = useAgents(agentexClient);
  const { agentName, updateParams } = useSafeSearchParams();
  const [prompt, setPrompt] = useState<string>('');
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [localAgentName, setLocalAgentName] = useLocalStorageState<
    string | undefined
  >('lastSelectedAgent', undefined);

  useEffect(() => {
    if (!isLoading) {
      if (!agentName && localAgentName) {
        updateParams({ [SearchParamKey.AGENT_NAME]: localAgentName });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

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

  // Scroll detection - track if user is near bottom
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) {
      setShowScrollButton(false);
      return;
    }

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

      const scrollThreshold = 100; // pixels from bottom
      const isNearBottom = distanceFromBottom < scrollThreshold;

      setShowScrollButton(!isNearBottom);
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [taskID]);

  const scrollToBottom = useCallback(() => {
    if (!scrollContainerRef.current) return;
    scrollContainerRef.current.scrollTo({
      top: scrollContainerRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [scrollContainerRef]);

  useEffect(() => {
    if (scrollContainerRef.current && taskID) {
      setTimeout(() => {
        scrollToBottom();
      }, 150);
    }
  }, [scrollToBottom, taskID]);

  return (
    <AnimatePresence>
      <motion.div
        layout
        className={`relative flex h-full flex-1 flex-col ${!taskID ? 'justify-center' : 'justify-between'}`}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
      >
        {taskID && agentName && (
          <motion.div
            key="topbar"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
          >
            <TaskTopBar
              taskId={taskID}
              isTracesSidebarOpen={isTracesSidebarOpen}
              toggleTracesSidebar={toggleTracesSidebar}
              agents={agents}
              onAgentChange={handleSelectAgent}
            />
          </motion.div>
        )}

        {taskID ? (
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
                  <MemoizedTaskMessagesComponent taskId={taskID} />
                </TaskProvider>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="home-view"
            className="flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
          >
            <div className="flex flex-col items-center justify-center px-4">
              <div className="mb-6 text-2xl font-bold">Agentex</div>
              <AgentsList agents={agents} isLoading={isLoading} />
              <button
                onClick={() => {
                  updateParams({ [SearchParamKey.AGENT_NAME]: null });
                  setLocalAgentName(undefined);
                }}
                className={`text-muted-foreground cursor-pointer text-xs transition-opacity duration-200 hover:underline ${
                  agentName ? 'opacity-100' : 'pointer-events-none opacity-0'
                }`}
              >
                view all agents
              </button>
            </div>
          </motion.div>
        )}

        <motion.div
          layout="position"
          className="relative flex w-full justify-center px-4 py-4 sm:px-6 md:px-8"
          transition={{
            layout: {
              type: 'spring',
              damping: 40,
              stiffness: 300,
              mass: 0.8,
            },
          }}
        >
          {taskID && (
            <AnimatePresence>
              {showScrollButton && (
                <motion.div
                  className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-4 -translate-x-1/2"
                  initial={{ y: 30, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: 30, opacity: 0 }}
                  transition={{
                    duration: 0.2,
                    type: 'spring',
                    stiffness: 300,
                    damping: 35,
                    mass: 0.8,
                  }}
                >
                  <IconButton
                    className="pointer-events-auto size-10 rounded-full shadow-lg"
                    onClick={scrollToBottom}
                    icon={ArrowDown}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          )}

          <div className="w-full max-w-3xl">
            <PromptInput prompt={prompt} setPrompt={setPrompt} />
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

type Props = {
  sgpAppURL: string;
  agentexAPIBaseURL: string;
};

export function MainContent({ sgpAppURL, agentexAPIBaseURL }: Props) {
  return (
    <QueryProvider>
      <AgentexProvider
        sgpAppURL={sgpAppURL ?? ''}
        agentexAPIBaseURL={agentexAPIBaseURL}
      >
        <Suspense fallback={<div>Loading...</div>}>
          <NoAgentImpl />
        </Suspense>
      </AgentexProvider>
      <ToastContainer />
    </QueryProvider>
  );
}
