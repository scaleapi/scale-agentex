import { useState, useRef, useEffect, useCallback } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDown } from 'lucide-react';

import { IconButton } from '@/components/agentex/icon-button';
import { PromptInput } from '@/components/agentex/prompt-input';
import { TaskTopBar } from '@/components/agentex/task-top-bar';
import { useAgentexClient } from '@/components/providers';
import { useAgents } from '@/hooks/use-agents';
import {
  useSafeSearchParams,
  SearchParamKey,
} from '@/hooks/use-safe-search-params';

import { ChatView } from './chat-view';
import { HomeView } from './home-view';

type ContentAreaProps = {
  isTracesSidebarOpen: boolean;
  toggleTracesSidebar: () => void;
};

export function PrimaryContent({
  isTracesSidebarOpen,
  toggleTracesSidebar,
}: ContentAreaProps) {
  const { taskID } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();
  const { data: agents = [] } = useAgents(agentexClient);
  const { agentName, updateParams } = useSafeSearchParams();
  const [prompt, setPrompt] = useState<string>('');
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);

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

      {taskID ? <ChatView taskID={taskID} /> : <HomeView />}

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
  );
}
