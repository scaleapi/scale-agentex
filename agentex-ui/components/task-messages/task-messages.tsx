import { Fragment, memo, useEffect, useMemo, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';

import { useAgentexClient } from '@/components/providers';
import { TaskMessageDataContent } from '@/components/task-messages/task-message-data-content';
import { TaskMessageReasoning } from '@/components/task-messages/task-message-reasoning-content';
import { TaskMessageScrollContainer } from '@/components/task-messages/task-message-scroll-container';
import { TaskMessageTextContent } from '@/components/task-messages/task-message-text-content';
import { TaskMessageToolPair } from '@/components/task-messages/task-message-tool-pair';
import { ShimmeringText } from '@/components/ui/shimmering-text';
import { useTaskMessages } from '@/hooks/use-task-messages';

import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';

type TaskMessagesProps = {
  taskId: string;
};
type MessagePair = {
  id: string;
  userMessage: TaskMessage;
  agentMessages: TaskMessage[];
};

function TaskMessagesImpl({ taskId }: TaskMessagesProps) {
  const lastPairRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState<number>(0);

  const { agentexClient } = useAgentexClient();

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
    const rpcStatus = queryData?.rpcStatus;

    return (
      hasNoAgentMessages && (rpcStatus === 'pending' || rpcStatus === 'success')
    );
  }, [messagePairs, queryData?.rpcStatus]);

  useEffect(() => {
    const measureHeight = () => {
      if (containerRef.current) {
        let element = containerRef.current.parentElement;
        while (element) {
          const overflowY = window.getComputedStyle(element).overflowY;
          if (overflowY === 'auto' || overflowY === 'scroll') {
            setContainerHeight(element.clientHeight);
            return;
          }
          element = element.parentElement;
        }
      }
    };

    measureHeight();

    window.addEventListener('resize', measureHeight);
    return () => window.removeEventListener('resize', measureHeight);
  }, [messages]);

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
