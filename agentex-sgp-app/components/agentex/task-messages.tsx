import React, { memo, useEffect, useMemo, useRef, useState } from 'react';

import { AnimatePresence } from 'framer-motion';

import { AnimatedMessageWrapper } from '@/components/agentex/animated-message-wrapper';
import { TaskMessageDataContentComponent } from '@/components/agentex/task-message-data-content';
import { TaskMessageReasoning } from '@/components/agentex/task-message-reasoning-content';
import { TaskMessageScrollContainer } from '@/components/agentex/task-message-scroll-container';
import { TaskMessageTextContentComponent } from '@/components/agentex/task-message-text-content';
import { MemoizedTaskMessageToolPairComponent } from '@/components/agentex/task-message-tool-pair';
import { useAgentexClient } from '@/components/providers';
import { useTaskMessages } from '@/hooks/use-task-messages';

import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';

type TaskMessageComponentProps = {
  message: TaskMessage;
  key?: string;
};

function TaskMessageComponent({ message, key }: TaskMessageComponentProps) {
  if (message.content.type === 'text') {
    return (
      <TaskMessageTextContentComponent content={message.content} key={key} />
    );
  }
  if (message.content.type === 'data') {
    return (
      <TaskMessageDataContentComponent content={message.content} key={key} />
    );
  }
  if (message.content.type === 'reasoning') {
    // TODO: Fix check for streaming status to get accurate isStreaming status
    return <TaskMessageReasoning message={message} />;
  }

  message.content.type satisfies 'tool_request' | 'tool_response' | undefined;

  return null;
}

const MemoizedTaskMessageComponent = memo(TaskMessageComponent);

type TaskMessagesComponentProps = {
  taskId: string;
  autoScrollEnabled?: boolean;
};
// Type for a message pair (user message + agent response(s))
type MessagePair = {
  id: string;
  userMessage: TaskMessage;
  agentMessages: TaskMessage[];
};

function MemoizedTaskMessagesComponentImpl({
  taskId,
  autoScrollEnabled = true,
}: TaskMessagesComponentProps) {
  const lastPairRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState<number>(0);

  const { agentexClient } = useAgentexClient();

  // Use query hook to get messages from cache if taskId is provided
  const { data: queryData } = useTaskMessages({ agentexClient, taskId });

  // Prefer query data if available, otherwise use prop messages
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

  // Group messages into pairs (user message + subsequent agent messages)
  const messagePairs = useMemo<MessagePair[]>(() => {
    const pairs: MessagePair[] = [];
    let currentUserMessage: TaskMessage | null = null;
    let currentAgentMessages: TaskMessage[] = [];

    for (const message of messages) {
      const isUserMessage = message.content.author === 'user';

      if (isUserMessage) {
        // Save previous pair if exists
        if (currentUserMessage) {
          pairs.push({
            id: currentUserMessage.id || `pair-${pairs.length}`,
            userMessage: currentUserMessage,
            agentMessages: currentAgentMessages,
          });
        }
        // Start new pair
        currentUserMessage = message;
        currentAgentMessages = [];
      } else {
        // Add to current agent messages
        if (currentUserMessage) {
          currentAgentMessages.push(message);
        } else {
          // Agent message without a user message - create a pair with just agent messages
          pairs.push({
            id: message.id || `pair-${pairs.length}`,
            userMessage: message, // Use the agent message as the "user" message
            agentMessages: [],
          });
        }
      }
    }

    // Add the last pair
    if (currentUserMessage) {
      pairs.push({
        id: currentUserMessage.id || `pair-${pairs.length}`,
        userMessage: currentUserMessage,
        agentMessages: currentAgentMessages,
      });
    }

    return pairs;
  }, [messages]);

  // Measure the scrollable container height
  useEffect(() => {
    const measureHeight = () => {
      if (containerRef.current) {
        // Walk up the DOM tree to find the scrollable container (has overflow-y-auto)
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

    // Measure on mount and when messages change
    measureHeight();

    // Recalculate on window resize
    window.addEventListener('resize', measureHeight);
    return () => window.removeEventListener('resize', measureHeight);
  }, [messages]);

  // Scroll to top when new message arrives (only if auto-scroll enabled)
  useEffect(() => {
    if (!autoScrollEnabled) return;

    const previousCount = previousMessageCountRef.current;
    const currentCount = messages.length;

    if (currentCount > previousCount && lastPairRef.current) {
      setTimeout(() => {
        lastPairRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      }, 100);
    }

    previousMessageCountRef.current = currentCount;
  }, [messages.length, autoScrollEnabled]);

  // Helper function to render a message
  const renderMessage = (message: TaskMessage) => {
    switch (message.content.type) {
      case 'text':
      case 'data':
      case 'reasoning':
        return <MemoizedTaskMessageComponent message={message} />;
      case 'tool_request':
        return (
          <MemoizedTaskMessageToolPairComponent
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
      <AnimatePresence initial={false}>
        {messagePairs.map((pair, index) => {
          const isLastPair = index === messagePairs.length - 1;

          return (
            <TaskMessageScrollContainer
              key={pair.id}
              ref={isLastPair ? lastPairRef : null}
              isLastPair={isLastPair}
              containerHeight={containerHeight}
            >
              <AnimatedMessageWrapper
                messageId={pair.id}
                hasAnimated={pair.agentMessages.length > 0}
              >
                {renderMessage(pair.userMessage)}
              </AnimatedMessageWrapper>
              {pair.agentMessages.map(agentMessage => (
                <React.Fragment key={agentMessage.id}>
                  {renderMessage(agentMessage)}
                </React.Fragment>
              ))}
            </TaskMessageScrollContainer>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

const MemoizedTaskMessagesComponent = memo(MemoizedTaskMessagesComponentImpl);

export { MemoizedTaskMessagesComponent, TaskMessageComponent };
