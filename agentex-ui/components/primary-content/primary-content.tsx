import { useState, useRef, useEffect, useCallback } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDown } from 'lucide-react';

import { ChatView } from '@/components/primary-content/chat-view';
import { HomeView } from '@/components/primary-content/home-view';
import { PromptInput } from '@/components/primary-content/prompt-input';
import { useAgentexClient } from '@/components/providers';
import { IconButton } from '@/components/ui/icon-button';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useWaitingForHuman } from '@/hooks/use-waiting-for-human';

type ContentAreaProps = {
  isTracesSidebarOpen: boolean;
  toggleTracesSidebar: () => void;
  isArtifactPanelOpen: boolean;
};

export function PrimaryContent({
  isTracesSidebarOpen,
  toggleTracesSidebar,
  isArtifactPanelOpen,
}: ContentAreaProps) {
  const { taskID } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();

  const [prompt, setPrompt] = useState<string>('');
  const [showScrollButton, setShowScrollButton] = useState(false);
  const { isWaiting: isWaitingForHuman } = useWaitingForHuman({
    agentexClient,
    taskId: taskID || '',
  });

  const scrollContainerRef = useRef<HTMLDivElement>(null);

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

      const scrollThreshold = 100;
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
      {taskID ? (
        <ChatView
          taskID={taskID}
          isTracesSidebarOpen={isTracesSidebarOpen}
          toggleTracesSidebar={toggleTracesSidebar}
          scrollContainerRef={scrollContainerRef}
          setPrompt={setPrompt}
          isArtifactPanelOpen={isArtifactPanelOpen}
        />
      ) : (
        <HomeView />
      )}
      {taskID && !isWaitingForHuman && (
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
          <AnimatePresence>
            {taskID && showScrollButton && (
              <ScrollToBottomButton scrollToBottom={scrollToBottom} />
            )}
          </AnimatePresence>

          <PromptInput prompt={prompt} setPrompt={setPrompt} />
        </motion.div>
      )}
    </motion.div>
  );
}

function ScrollToBottomButton({
  scrollToBottom,
}: {
  scrollToBottom: () => void;
}) {
  return (
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
  );
}
