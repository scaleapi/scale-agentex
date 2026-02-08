import { memo, useState, useMemo, useRef, useEffect } from 'react';

import { motion } from 'framer-motion';
import { BrainIcon, ChevronDownIcon } from 'lucide-react';

import { MarkdownResponse } from '@/components/task-messages/markdown-response';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useTaskMessages } from '@/hooks/use-task-messages';
import { calculateThinkingTime } from '@/lib/date-utils';
import { cn } from '@/lib/utils';

import { useAgentexClient } from '../providers/agentex-provider';
import { Collapsible } from '../ui/collapsible';
import { ShimmeringText } from '../ui/shimmering-text';

import type { TaskMessage } from 'agentex/resources';

type TaskMessageReasoningProps = {
  message: TaskMessage;
};

function TaskMessageReasoningImpl({ message }: TaskMessageReasoningProps) {
  const [isCollapsed, setIsCollapsed] = useState(true);
  const [showTopBlur, setShowTopBlur] = useState(false);
  const [showBottomBlur, setShowBottomBlur] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const { taskID } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();

  const { data: queryData } = useTaskMessages({
    agentexClient,
    taskId: taskID ?? '',
  });
  const messages = queryData?.messages ?? [];
  const messageIndex = messages.findIndex(m => m.id === message.id);
  const nextMessage = messageIndex !== -1 ? messages[messageIndex + 1] : null;

  const reasoningInProgress = useMemo(() => {
    return message.streaming_status === 'IN_PROGRESS' && !nextMessage;
  }, [message.streaming_status, nextMessage]);

  const reasoningHeaderText = useMemo(() => {
    if (reasoningInProgress) {
      return `Planning next steps...`;
    }
    const reasoningTime = calculateThinkingTime(
      message,
      nextMessage?.created_at ?? message.updated_at
    );
    if (reasoningTime) {
      return `Planned for ${reasoningTime} seconds`;
    }
    return `Planned for some time`;
  }, [reasoningInProgress, message, nextMessage]);

  const reasoningText = useMemo(() => {
    if (message.content.type !== 'reasoning') {
      throw new Error('Message content is not a ReasoningContent');
    }
    return [
      ...(message.content.content ?? []),
      ...(message.content.summary ?? []),
    ].join('\n\n');
  }, [message.content]);

  const updateBlurEffects = () => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const isScrollable = scrollHeight > clientHeight;

    setShowTopBlur(isScrollable && scrollTop > 10);
    setShowBottomBlur(
      isScrollable && scrollTop < scrollHeight - clientHeight - 10
    );
  };

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    updateBlurEffects();
    const resizeObserver = new ResizeObserver(updateBlurEffects);
    resizeObserver.observe(container);

    return () => resizeObserver.disconnect();
  }, [isCollapsed, reasoningText]);

  return (
    <motion.div
      className="w-full"
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.3,
        ease: 'easeInOut',
      }}
    >
      <button
        className="mb-2 flex items-center gap-2"
        type="button"
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <BrainIcon className="size-4" />
        <ShimmeringText
          enabled={reasoningInProgress}
          text={reasoningHeaderText}
        />

        <ChevronDownIcon
          className={cn(
            'size-4 transition-transform duration-500',
            isCollapsed ? '' : 'scale-y-[-1]'
          )}
        />
      </button>
      <Collapsible collapsed={isCollapsed}>
        <div className="relative ml-6">
          <div
            className={cn(
              'pointer-events-none absolute inset-x-0 top-0 z-10 h-8 bg-gradient-to-b from-white to-transparent transition-opacity',
              showTopBlur ? 'opacity-100' : 'opacity-0'
            )}
          />
          <div
            ref={scrollContainerRef}
            onScroll={updateBlurEffects}
            className="max-h-48 overflow-y-auto"
          >
            <MarkdownResponse className="grid border-l-4 border-gray-300 pl-3 text-gray-500">
              {reasoningText}
            </MarkdownResponse>
          </div>
          <div
            className={cn(
              'pointer-events-none absolute inset-x-0 bottom-0 z-10 h-8 bg-gradient-to-t from-white to-transparent transition-opacity',
              showBottomBlur ? 'opacity-100' : 'opacity-0'
            )}
          />
        </div>
      </Collapsible>
    </motion.div>
  );
}

const TaskMessageReasoning = memo(TaskMessageReasoningImpl);

export { TaskMessageReasoning };
