import { Fragment, memo, useEffect, useMemo, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';

import { HumanResponseForm } from '@/components/agentex/project/human-response-form';
import { TaskMessageDataContent } from '@/components/agentex/task-message-data-content';
import { TaskMessageReasoning } from '@/components/agentex/task-message-reasoning-content';
import { TaskMessageScrollContainer } from '@/components/agentex/task-message-scroll-container';
import { TaskMessageTextContent } from '@/components/agentex/task-message-text-content';
import { TaskMessageToolPair } from '@/components/agentex/task-message-tool-pair';
import { useAgentexClient } from '@/components/providers';
import { ShimmeringText } from '@/components/ui/shimmering-text';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
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
  userMessage: TaskMessage | null;
  agentMessages: TaskMessage[];
};

function TaskMessagesImpl({ taskId }: TaskMessagesProps) {
  const lastPairRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState<number>(0);

  const { agentexClient } = useAgentexClient();
  const { agentName } = useSafeSearchParams();

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

  // Track which user messages are responses to wait_for_human tools
  const userResponseToWaitForHumanIds = useMemo(() => {
    const ids = new Set<string>();

    for (let i = 0; i < messages.length; i++) {
      const message = messages[i];
      if (
        message &&
        message.content.type === 'tool_request' &&
        message.content.name === 'wait_for_human'
      ) {
        // Look for the next user message
        for (let j = i + 1; j < messages.length; j++) {
          const nextMsg = messages[j];
          if (
            nextMsg &&
            nextMsg.content.type === 'text' &&
            nextMsg.content.author === 'user'
          ) {
            ids.add(nextMsg.id!);
            break;
          }
          // Stop if we hit a tool_response
          if (
            nextMsg &&
            nextMsg.content.type === 'tool_response' &&
            (nextMsg.content as ToolResponseContent).tool_call_id ===
              message.content.tool_call_id
          ) {
            break;
          }
        }
      }
    }

    return ids;
  }, [messages]);

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
            userMessage: null,
            agentMessages: [message],
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
    // Skip user messages that are responses to wait_for_human tools
    if (
      message.id &&
      message.content.type === 'text' &&
      message.content.author === 'user' &&
      userResponseToWaitForHumanIds.has(message.id)
    ) {
      return null;
    }

    switch (message.content.type) {
      case 'text':
        return <TaskMessageTextContent content={message.content} />;
      case 'data':
        return <TaskMessageDataContent content={message.content} />;
      case 'reasoning':
        return <TaskMessageReasoning message={message} />;
      case 'tool_request': {
        const toolRequestMessage = message as TaskMessage & {
          content: ToolRequestContent;
        };
        const toolResponseMessage = toolCallIdToResponseMap.get(
          message.content.tool_call_id
        );

        // Check if this is a wait_for_human tool
        if (message.content.name === 'wait_for_human' && agentName) {
          const params = message.content.arguments as { message?: string };

          // Find the user response that comes after this tool request
          const messageIndex = messages.findIndex(m => m.id === message.id);
          let userResponse: string | null = null;

          if (messageIndex !== -1) {
            // Look for the next user message after this tool
            for (let i = messageIndex + 1; i < messages.length; i++) {
              const nextMsg = messages[i];
              if (
                nextMsg &&
                nextMsg.content.type === 'text' &&
                nextMsg.content.author === 'user'
              ) {
                userResponse = nextMsg.content.content;
                break;
              }
              // Stop if we hit a tool_response for this tool
              if (
                nextMsg &&
                nextMsg.content.type === 'tool_response' &&
                (nextMsg.content as ToolResponseContent).tool_call_id ===
                  message.content.tool_call_id
              ) {
                break;
              }
            }
          }

          return (
            <HumanResponseForm
              message={params?.message || ''}
              taskId={taskId}
              agentName={agentName}
              userResponse={userResponse}
              isResponded={userResponse !== null}
            />
          );
        }

        return (
          <TaskMessageToolPair
            toolRequestMessage={toolRequestMessage}
            toolResponseMessage={toolResponseMessage}
          />
        );
      }
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
