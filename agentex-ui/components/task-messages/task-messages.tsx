import { Fragment, memo, useEffect, useMemo, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';

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
};
type MessagePair = {
  id: string;
  userMessage: TaskMessage | null;
  agentMessages: TaskMessage[];
};

function TaskMessagesImpl({ taskId, headerRef }: TaskMessagesProps) {
  const lastPairRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState<number>(0);

  const { agentexClient, sgpAppURL } = useAgentexClient();
  const { agentName } = useSafeSearchParams();
  const { data: agents = [] } = useAgents(agentexClient);
  const agent = agents.find(a => a.name === agentName);

  const { data: queryData } = useTaskMessages({ agentexClient, taskId });

  const messages = useMemo(() => queryData?.messages ?? [], [queryData]);
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

  const shouldShowThinkingForLastPair = useMemo(() => {
    if (messagePairs.length === 0) return false;

    const lastPair = messagePairs[messagePairs.length - 1]!;
    const hasNoAgentMessages = lastPair.agentMessages.length === 0;
    const hasUserMessage = lastPair.userMessage !== null;
    const rpcStatus = queryData?.rpcStatus;

    return (
      hasUserMessage &&
      hasNoAgentMessages &&
      (rpcStatus === 'pending' || rpcStatus === 'success')
    );
  }, [messagePairs, queryData?.rpcStatus]);

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

  useEffect(() => {
    const previousCount = previousMessageCountRef.current;
    const currentCount = messagePairs.length;

    if (currentCount > previousCount && lastPairRef.current) {
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
