import {
  Fragment,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

import { useAgentexClient } from '@/components/providers';
import { MessageFeedback } from '@/components/task-messages/message-feedback';
import { TaskMessageDataContent } from '@/components/task-messages/task-message-data-content';
import { TaskMessageReasoning } from '@/components/task-messages/task-message-reasoning-content';
import { TaskMessageScrollContainer } from '@/components/task-messages/task-message-scroll-container';
import { TaskMessageTextContent } from '@/components/task-messages/task-message-text-content';
import { TaskMessageToolPair } from '@/components/task-messages/task-message-tool-pair';
import { ShimmeringText } from '@/components/ui/shimmering-text';
import { useAgents } from '@/hooks/use-agents';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useTaskMessages } from '@/hooks/use-task-messages';

import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';

type TaskMessagesProps = {
  taskId: string;
  headerRef: React.RefObject<HTMLDivElement | null>;
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
};
type MessagePair = {
  id: string;
  userMessage: TaskMessage | null;
  agentMessages: TaskMessage[];
};

function TaskMessagesImpl({
  taskId,
  headerRef,
  scrollContainerRef,
}: TaskMessagesProps) {
  const lastPairRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState<number>(0);
  const isInitialLoadRef = useRef(true);
  const previousLastPairIdRef = useRef<string | null>(null);
  const previousPagesScrollHeightRef = useRef<number | null>(null);

  // Reset scroll state when switching tasks
  useEffect(() => {
    isInitialLoadRef.current = true;
    previousLastPairIdRef.current = null;
    previousPagesScrollHeightRef.current = null;
  }, [taskId]);

  const { agentexClient, sgpAppURL } = useAgentexClient();
  const { agentName } = useSafeSearchParams();
  const { data: agents = [] } = useAgents(agentexClient);
  const agent = agents.find(a => a.name === agentName);

  const {
    messages,
    rpcStatus,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useTaskMessages({ agentexClient, taskId });

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
    let pairStarted = false;

    for (const message of messages) {
      const isUserMessage = message.content.author === 'user';

      if (isUserMessage) {
        if (pairStarted) {
          pairs.push({
            id:
              currentUserMessage?.id ||
              currentAgentMessages[0]?.id ||
              `pair-${pairs.length}`,
            userMessage: currentUserMessage,
            agentMessages: currentAgentMessages,
          });
        }
        currentUserMessage = message;
        currentAgentMessages = [];
        pairStarted = true;
      } else {
        if (!pairStarted) {
          currentUserMessage = null;
          currentAgentMessages = [];
          pairStarted = true;
        }
        currentAgentMessages.push(message);
      }
    }

    if (pairStarted) {
      pairs.push({
        id:
          currentUserMessage?.id ||
          currentAgentMessages[0]?.id ||
          `pair-${pairs.length}`,
        userMessage: currentUserMessage,
        agentMessages: currentAgentMessages,
      });
    }

    return pairs;
  }, [messages]);

  const pendingToolCallIds = useMemo(() => {
    const pending = new Set<string>();
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i]!;
      if (msg.content.type === 'tool_request') {
        if (!toolCallIdToResponseMap.has(msg.content.tool_call_id)) {
          pending.add(msg.content.tool_call_id);
        }
      } else if (msg.content.type !== 'tool_response') {
        break;
      }
    }
    return pending;
  }, [messages, toolCallIdToResponseMap]);

  const shouldShowThinkingForLastPair = useMemo(() => {
    if (messagePairs.length === 0) return false;
    if (rpcStatus !== 'pending' && rpcStatus !== 'success') return false;

    const lastPair = messagePairs[messagePairs.length - 1]!;

    // No agent messages yet — waiting for first response
    if (lastPair.agentMessages.length === 0) {
      return lastPair.userMessage !== null;
    }

    const lastAgentMessage =
      lastPair.agentMessages[lastPair.agentMessages.length - 1]!;
    const lastType = lastAgentMessage.content.type;

    // Already have text streaming or complete — not "thinking"
    if (lastType === 'text') return false;

    // Tool or reasoning still in progress — show their own indicator, not "Thinking..."
    if (lastAgentMessage.streaming_status === 'IN_PROGRESS') return false;
    if (
      lastType === 'tool_request' &&
      pendingToolCallIds.has(lastAgentMessage.content.tool_call_id)
    )
      return false;

    // Last message is a completed tool_request, tool_response, reasoning, or data
    // with no following text — agent is thinking about the next step
    return true;
  }, [messagePairs, rpcStatus, pendingToolCallIds]);

  // Measure container height for last-pair min-height
  useEffect(() => {
    const measureHeight = () => {
      if (containerRef.current) {
        let element = containerRef.current.parentElement;
        while (element) {
          const overflowY = window.getComputedStyle(element).overflowY;
          if (overflowY === 'auto' || overflowY === 'scroll') {
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

  // Scroll to bottom when NEW messages arrive at the end.
  // Track the last pair ID — only scroll when it changes (new messages),
  // not when older messages load at the top (which also increases length).
  const lastPairId = messagePairs[messagePairs.length - 1]?.id ?? null;

  useEffect(() => {
    if (!lastPairId || lastPairId === previousLastPairIdRef.current) return;

    const isInitial = isInitialLoadRef.current;
    previousLastPairIdRef.current = lastPairId;

    const container = scrollContainerRef.current;

    if (isInitial) {
      // On initial load, wait for the browser to paint all content, then
      // jump to the absolute bottom of the scroll container. Using
      // requestAnimationFrame ensures layout is complete — scrollIntoView
      // on a specific element can misfire if content is still rendering.
      isInitialLoadRef.current = false;
      requestAnimationFrame(() => {
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      });
    } else if (lastPairRef.current) {
      setTimeout(() => {
        lastPairRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      }, 100);
    }
  }, [lastPairId, scrollContainerRef]);

  // Scroll position preservation after older pages load
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || previousPagesScrollHeightRef.current === null) return;

    const addedHeight =
      container.scrollHeight - previousPagesScrollHeightRef.current;
    if (addedHeight > 0) {
      container.scrollTop += addedHeight;
    }
    previousPagesScrollHeightRef.current = null;
  }, [messages, scrollContainerRef]);

  const handleLoadOlder = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container) {
      previousPagesScrollHeightRef.current = container.scrollHeight;
    }
    fetchNextPage();
  }, [fetchNextPage, scrollContainerRef]);

  // Scroll event listener: fetch older messages when user scrolls near the top.
  // Unlike IntersectionObserver, scroll events don't fire on mount — only on
  // actual scroll actions (user or programmatic).
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const onScroll = () => {
      if (container.scrollTop < 100 && hasNextPage && !isFetchingNextPage) {
        handleLoadOlder();
      }
    };

    container.addEventListener('scroll', onScroll, { passive: true });
    return () => container.removeEventListener('scroll', onScroll);
  }, [scrollContainerRef, hasNextPage, isFetchingNextPage, handleLoadOlder]);

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
            isInProgress={pendingToolCallIds.has(message.content.tool_call_id)}
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
      {isFetchingNextPage && (
        <div className="flex w-full justify-center py-3">
          <Loader2 className="text-muted-foreground size-5 animate-spin" />
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
              {pair.userMessage && renderMessage(pair.userMessage)}
              {pair.agentMessages.map(agentMessage => (
                <Fragment key={agentMessage.id}>
                  <div className="group/feedback">
                    {renderMessage(agentMessage)}
                    {sgpAppURL &&
                      agentMessage.id &&
                      agentMessage.content.type === 'text' &&
                      agentMessage.content.author === 'agent' &&
                      agentMessage.streaming_status !== 'IN_PROGRESS' && (
                        <MessageFeedback
                          messageId={agentMessage.id}
                          taskId={taskId}
                          agentMessageContent={agentMessage.content.content}
                          userMessageContent={
                            pair.userMessage?.content.type === 'text'
                              ? pair.userMessage.content.content
                              : ''
                          }
                          agentName={agent?.name}
                          agentId={agent?.id}
                          agentAcpType={agent?.acp_type}
                        />
                      )}
                  </div>
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
