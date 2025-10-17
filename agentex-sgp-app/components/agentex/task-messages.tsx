import { TaskMessageTextContentComponent } from '@/components/agentex/task-message-text-content';
import { TaskMessageDataContentComponent } from '@/components/agentex/task-message-data-content';
import { TaskMessageReasoningContentComponent } from '@/components/agentex/task-message-reasoning-content';
import {
  MemoizedTaskMessageToolPairComponent,
  TaskMessageToolPairComponent,
} from '@/components/agentex/task-message-tool-pair';
import { TaskMessageScrollContainer } from '@/components/agentex/task-message-scroll-container';
import { AnimatedMessageWrapper } from '@/components/agentex/animated-message-wrapper';
import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';
import React, { memo, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence } from 'framer-motion';

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
    return (
      <TaskMessageReasoningContentComponent
        content={message.content}
        isStreaming={message.streaming_status === 'IN_PROGRESS'}
      />
    );
  }

  message.content.type satisfies 'tool_request' | 'tool_response' | undefined;

  return null;
}

const MemoizedTaskMessageComponent = memo(TaskMessageComponent);

type TaskMessagesComponentProps = {
  messages: TaskMessage[];
};

function TaskMessagesComponent({ messages }: TaskMessagesComponentProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const toolCallIdToResponseMap = new Map(
    messages
      .filter(
        (m): m is TaskMessage & { content: ToolResponseContent } =>
          m.content.type === 'tool_response'
      )
      .map((m) => [m.content.tool_call_id, m])
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col gap-4">
      {messages.map((m) => {
        const { content } = m;
        switch (content.type) {
          case 'text':
          case 'data':
          case 'reasoning':
            return (
              <TaskMessageComponent
                key={m.id || `msg-${Math.random()}`}
                message={m}
              />
            );
          case 'tool_request':
            return (
              <TaskMessageToolPairComponent
                key={m.id || `tool-${Math.random()}`}
                toolRequestMessage={{
                  ...m,
                  content,
                }}
                toolResponseMessage={toolCallIdToResponseMap.get(
                  content.tool_call_id
                )}
              />
            );
          case 'tool_response':
            return null;
          default:
            content.type satisfies undefined;
            return null;
        }
      })}
      <div ref={messagesEndRef} />
    </div>
  );
}

// Type for a message pair (user message + agent response(s))
type MessagePair = {
  id: string;
  userMessage: TaskMessage;
  agentMessages: TaskMessage[];
};

function MemoizedTaskMessagesComponentImpl({
  messages,
}: TaskMessagesComponentProps) {
  const lastPairRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState<number>(0);
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
          .map((m) => [m.content.tool_call_id, m])
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

  // Measure the grandparent container height (the scrollable area)
  useEffect(() => {
    const measureHeight = () => {
      if (containerRef.current) {
        // Get the grandparent (scrollable container)
        const grandparent = containerRef.current.parentElement;
        if (grandparent) {
          setContainerHeight(grandparent.clientHeight);
        }
      }
    };

    // Measure on mount and when messages change
    measureHeight();

    // Recalculate on window resize
    window.addEventListener('resize', measureHeight);
    return () => window.removeEventListener('resize', measureHeight);
  }, [messages]);

  // Scroll to top when new message arrives
  useEffect(() => {
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
  }, [messages.length]);

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
    <div ref={containerRef} className="flex flex-col w-full items-center">
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
              {pair.agentMessages.map((agentMessage) => (
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

export { MemoizedTaskMessagesComponent, TaskMessagesComponent };
