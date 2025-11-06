import { memo, useState, useMemo } from 'react';

import { motion } from 'framer-motion';
import { BrainIcon, ChevronDownIcon } from 'lucide-react';

import { MarkdownResponse } from '@/components/task-messages/markdown-response';
import { calculateThinkingTime } from '@/lib/date-utils';
import { cn } from '@/lib/utils';

import { Collapsible } from '../ui/collapsible';
import { ShimmeringText } from '../ui/shimmering-text';

import type { TaskMessage } from 'agentex/resources';

type TaskMessageReasoningProps = {
  message: TaskMessage;
};

function TaskMessageReasoningImpl({ message }: TaskMessageReasoningProps) {
  const [isCollapsed, setIsCollapsed] = useState(true);
  const reasoningInProgress = useMemo(() => {
    return message.streaming_status === 'IN_PROGRESS';
  }, [message.streaming_status]);
  const reasoningHeaderText = useMemo(() => {
    if (reasoningInProgress) {
      return `Planning next steps...`;
    }
    const reasoningTime = calculateThinkingTime(message, message.updated_at);
    if (reasoningTime) {
      return `Planned for ${reasoningTime} seconds`;
    }
    return `Planned for some time`;
  }, [reasoningInProgress, message]);

  const reasoningText = useMemo(() => {
    if (message.content.type !== 'reasoning') {
      throw new Error('Message content is not a ReasoningContent');
    }
    return [
      ...(message.content.content ?? []),
      ...(message.content.summary ?? []),
    ].join('\n');
  }, [message.content]);

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
        <MarkdownResponse className="ml-6 grid border-l-4 border-gray-300 pl-3 text-gray-500">
          {reasoningText}
        </MarkdownResponse>
      </Collapsible>
    </motion.div>
  );
}

const TaskMessageReasoning = memo(TaskMessageReasoningImpl);

export { TaskMessageReasoning };
