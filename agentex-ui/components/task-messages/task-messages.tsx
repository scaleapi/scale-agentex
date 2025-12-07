import {
  Fragment,
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { AnimatePresence, motion } from 'framer-motion';

import { useAgentexClient } from '@/components/providers';
import { TaskMessageDataContent } from '@/components/task-messages/task-message-data-content';
import { TaskMessageReasoning } from '@/components/task-messages/task-message-reasoning-content';
import { TaskMessageScrollContainer } from '@/components/task-messages/task-message-scroll-container';
import { TaskMessageTextContent } from '@/components/task-messages/task-message-text-content';
import { TaskMessageToolPair } from '@/components/task-messages/task-message-tool-pair';
import { ShimmeringText } from '@/components/ui/shimmering-text';
import { Spinner } from '@/components/ui/spinner';
import { useInfiniteTaskMessages } from '@/hooks/use-infinite-task-messages';

import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';

type TaskMessagesProps = {
  taskId: string;
  headerRef: React.RefObject<HTMLDivElement | null>;
};
type MessagePair = {
  id: string;
  userMessage: TaskMessage;
  agentMessages: TaskMessage[];
};

function TaskMessagesImpl({ taskId, headerRef }: TaskMessagesProps) {
  const lastPairRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLElement | null>(null);
  const [containerHeight, setContainerHeight] = useState<number>(0);
  // Prevent IntersectionObserver from triggering during initial load
  const [isInitialScrollComplete, setIsInitialScrollComplete] = useState(false);
  const hasScrolledToBottomRef = useRef(false);
  // Track which taskId we last scrolled for (to handle task switching)
  const lastScrolledTaskIdRef = useRef<string | null>(null);
  // For scroll position preservation when loading older messages
  const previousScrollHeightRef = useRef<number>(0);
  const wasFetchingRef = useRef(false);

  const { agentexClient } = useAgentexClient();

  const {
    data: queryData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteTaskMessages({ agentexClient, taskId });

  const messages = useMemo(() => queryData?.messages ?? [], [queryData]);

  // Reset scroll state when switching tasks
  useEffect(() => {
    hasScrolledToBottomRef.current = false;
    setIsInitialScrollComplete(false);
    previousMessageCountRef.current = 0;
    // Don't reset lastScrolledTaskIdRef here - it's used to detect task changes
  }, [taskId]);

  // Check if any message is currently streaming
  const hasStreamingMessage = useMemo(
    () => messages.some(msg => msg.streaming_status === 'IN_PROGRESS'),
    [messages]
  );
  const previousMessageCountRef = useRef(messages.length);

  const toolCallIdToResponseMap = useMemo<
    Map<string, TaskMessage & { content: ToolResponseContent }>
  >(
    () =>
      new Map(
        messages
          .filter(
            (m): m is TaskMessage & { content: ToolResponseContent } =>
              m.content.type === 'tool_response'
          )
          .map(m => [m.content.tool_call_id, m])
      ),
    [messages]
  );

  const messagePairs = useMemo<MessagePair[]>(() => {
    const pairs: MessagePair[] = [];
    let currentUserMessage: TaskMessage | null = null;
    let currentAgentMessages: TaskMessage[] = [];

    for (const message of messages) {
      const isUserMessage = message.content.author === 'user';

      if (isUserMessage) {
        if (currentUserMessage) {
          pairs.push({
            id: currentUserMessage.id || `pair-${pairs.length}`,
            userMessage: currentUserMessage,
            agentMessages: currentAgentMessages,
          });
        }
        currentUserMessage = message;
        currentAgentMessages = [];
      } else {
        if (currentUserMessage) {
          currentAgentMessages.push(message);
        } else {
          pairs.push({
            id: message.id || `pair-${pairs.length}`,
            userMessage: message,
            agentMessages: [],
          });
        }
      }
    }

    if (currentUserMessage) {
      pairs.push({
        id: currentUserMessage.id || `pair-${pairs.length}`,
        userMessage: currentUserMessage,
        agentMessages: currentAgentMessages,
      });
    }

    return pairs;
  }, [messages]);

  const shouldShowThinkingForLastPair = useMemo(() => {
    if (messagePairs.length === 0) return false;

    const lastPair = messagePairs[messagePairs.length - 1]!;
    const hasNoAgentMessages = lastPair.agentMessages.length === 0;
    const lastUserMessageIsRecent =
      lastPair.userMessage.content.author === 'user';

    // Show thinking only when:
    // - User sent the last message AND no agent response yet AND nothing is streaming
    // Once streaming starts or agent responds, hide the thinking indicator
    return (
      hasNoAgentMessages && lastUserMessageIsRecent && !hasStreamingMessage
    );
  }, [messagePairs, hasStreamingMessage]);

  // Use IntersectionObserver to load more when sentinel becomes visible
  // Only enable after initial scroll to bottom is complete to avoid unwanted fetches
  useEffect(() => {
    const sentinel = loadMoreRef.current;
    if (!sentinel || !isInitialScrollComplete) {
      return;
    }

    const observer = new IntersectionObserver(
      entries => {
        const entry = entries[0];
        if (entry?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          // Save scroll height BEFORE fetching so we can restore position after
          if (scrollContainerRef.current) {
            previousScrollHeightRef.current =
              scrollContainerRef.current.scrollHeight;
          }
          fetchNextPage();
        }
      },
      { threshold: 0.1, rootMargin: '200px 0px 0px 0px' }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, isInitialScrollComplete]);

  useEffect(() => {
    const measureHeight = () => {
      if (containerRef.current) {
        let element = containerRef.current.parentElement;
        while (element) {
          const overflowY = window.getComputedStyle(element).overflowY;
          if (overflowY === 'auto' || overflowY === 'scroll') {
            // Store reference to scroll container for position preservation
            scrollContainerRef.current = element;
            setContainerHeight(
              element.clientHeight - (headerRef.current?.clientHeight ?? 0)
            );
            return;
          }
          element = element.parentElement;
        }
      }
    };

    measureHeight();

    window.addEventListener('resize', measureHeight);
    return () => window.removeEventListener('resize', measureHeight);
  }, [headerRef, messages]);

  // Preserve scroll position when older messages are loaded
  // This runs BEFORE paint to prevent visual jumping
  useLayoutEffect(() => {
    // Detect when fetching completes (was fetching, now not fetching)
    if (wasFetchingRef.current && !isFetchingNextPage) {
      const scrollContainer = scrollContainerRef.current;
      const previousScrollHeight = previousScrollHeightRef.current;

      if (scrollContainer && previousScrollHeight > 0) {
        const newScrollHeight = scrollContainer.scrollHeight;
        const heightDifference = newScrollHeight - previousScrollHeight;

        if (heightDifference > 0) {
          // Adjust scroll position by the height of newly added content
          scrollContainer.scrollTop += heightDifference;
        }

        // Reset for next pagination
        previousScrollHeightRef.current = 0;
      }
    }

    wasFetchingRef.current = isFetchingNextPage;
  }, [isFetchingNextPage]);

  // Initial scroll: use useLayoutEffect to scroll BEFORE browser paints
  // This prevents the user from seeing the scroll animation on first load
  useLayoutEffect(() => {
    // Check if we need to scroll: either first load OR task changed
    const needsScroll =
      !hasScrolledToBottomRef.current ||
      lastScrolledTaskIdRef.current !== taskId;

    if (needsScroll && messagePairs.length > 0 && lastPairRef.current) {
      // Scroll instantly before paint
      lastPairRef.current.scrollIntoView({
        behavior: 'instant',
        block: 'end',
      });

      hasScrolledToBottomRef.current = true;
      lastScrolledTaskIdRef.current = taskId;

      // Enable IntersectionObserver after a short delay
      setTimeout(() => {
        setIsInitialScrollComplete(true);
      }, 300);
    }
  }, [messagePairs.length, taskId]);

  // Subsequent new messages: smooth scroll (using regular useEffect)
  useEffect(() => {
    const previousCount = previousMessageCountRef.current;
    const currentCount = messagePairs.length;

    // Only handle NEW messages after initial load
    if (
      hasScrolledToBottomRef.current &&
      currentCount > previousCount &&
      lastPairRef.current
    ) {
      setTimeout(() => {
        lastPairRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      }, 100);
    }

    previousMessageCountRef.current = currentCount;
  }, [messagePairs.length]);

  const renderMessage = (message: TaskMessage) => {
    switch (message.content.type) {
      case 'text':
        return <TaskMessageTextContent content={message.content} />;
      case 'data':
        return <TaskMessageDataContent content={message.content} />;
      case 'reasoning':
        return <TaskMessageReasoning message={message} />;
      case 'tool_request':
        return (
          <TaskMessageToolPair
            toolRequestMessage={
              message as TaskMessage & { content: ToolRequestContent }
            }
            toolResponseMessage={toolCallIdToResponseMap.get(
              message.content.tool_call_id
            )}
          />
        );
      case 'tool_response':
        return null;
      default:
        message.content.type satisfies undefined;
        return null;
    }
  };

  return (
    <div
      ref={containerRef}
      className="flex w-full flex-1 flex-col items-center"
    >
      {/* Sentinel for IntersectionObserver - triggers loading older messages */}
      <div ref={loadMoreRef} className="h-1 w-full" />

      {/* Loading indicator for older messages */}
      {isFetchingNextPage && (
        <div className="flex justify-center py-4">
          <Spinner className="text-muted-foreground h-5 w-5" />
        </div>
      )}

      {/* Indicator when all history is loaded */}
      {!hasNextPage && messages.length > 0 && (
        <div className="text-muted-foreground py-4 text-center text-xs">
          Beginning of conversation
        </div>
      )}

      {messagePairs.map((pair, index) => {
        const isLastPair = index === messagePairs.length - 1;
        const shouldShowThinking = isLastPair && shouldShowThinkingForLastPair;

        return (
          <TaskMessageScrollContainer
            key={pair.id}
            ref={isLastPair ? lastPairRef : null}
            isLastPair={isLastPair}
            containerHeight={containerHeight}
          >
            <AnimatePresence>
              {renderMessage(pair.userMessage)}
              {pair.agentMessages.map(agentMessage => (
                <Fragment key={agentMessage.id}>
                  {renderMessage(agentMessage)}
                </Fragment>
              ))}
            </AnimatePresence>
            <AnimatePresence>
              {shouldShowThinking && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 10 }}
                  transition={{ duration: 0.3 }}
                  className="px-4 py-2"
                >
                  <ShimmeringText text="Thinking ..." enabled={true} />
                </motion.div>
              )}
            </AnimatePresence>
          </TaskMessageScrollContainer>
        );
      })}
    </div>
  );
}

const TaskMessages = memo(TaskMessagesImpl);

export { TaskMessages };
