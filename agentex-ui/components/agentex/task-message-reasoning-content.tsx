import { memo, useState } from 'react';

import { motion } from 'framer-motion';
import { BrainIcon, ChevronDownIcon } from 'lucide-react';

import { MarkdownResponse } from '@/components/agentex/markdown-response';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useTaskMessages } from '@/hooks/use-task-messages';
import { calculateThinkingTime } from '@/lib/date-utils';
import { cn } from '@/lib/utils';

import { useAgentexClient } from '../providers';
import { Collapsible } from '../ui/collapsible';
import { ShimmeringText } from '../ui/shimmering-text';

import type { TaskMessage } from 'agentex/resources';

type TaskMessageReasoningProps = {
  message: TaskMessage;
};

function TaskMessageReasoningImpl({ message }: TaskMessageReasoningProps) {
  const [isCollapsed, setIsCollapsed] = useState(true);

  const { taskID } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();

  const { data: queryData } = useTaskMessages({
    agentexClient,
    taskId: taskID ?? '',
  });
  const messages = queryData?.messages ?? [];
  const messageIndex = messages.findIndex(m => m.id === message.id);
  const nextMessage = messageIndex !== -1 ? messages[messageIndex + 1] : null;

  if (message.content.type !== 'reasoning') {
    throw new Error('Message content is not a ReasoningContent');
  }

  const reasoningText = [
    ...(message.content.content ?? []),
    ...(message.content.summary ?? []),
  ].join('\n');

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
          enabled={!nextMessage}
          text={
            nextMessage
              ? `Planned for ${calculateThinkingTime(message, nextMessage.created_at)} seconds`
              : `Planning next steps...`
          }
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
