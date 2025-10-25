import { useState } from 'react';

import { motion } from 'framer-motion';
import { BrainIcon, ChevronDownIcon } from 'lucide-react';

import { Response } from '@/components/ai-elements/response';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useTaskMessages } from '@/hooks/use-task-messages';
import { cn } from '@/lib/utils';

import { useAgentexClient } from '../providers';
import { Collapsible } from '../ui/collapsible';
import { ShimmeringText } from '../ui/shimmering-text';

import type { TaskMessage } from 'agentex/resources';

interface TaskMessageReasoningProps {
  message: TaskMessage;
}

export function TaskMessageReasoning({ message }: TaskMessageReasoningProps) {
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
      <div className="mb-2 flex items-center gap-2">
        <BrainIcon className="size-4" />
        <ShimmeringText
          enabled={!nextMessage}
          text={
            nextMessage
              ? `Planned for ${calculateThinkingTime(message, nextMessage.created_at)} seconds`
              : `Planning next steps...`
          }
        />
        <button onClick={() => setIsCollapsed(!isCollapsed)}>
          <ChevronDownIcon
            className={cn(
              'size-4 transition-transform duration-500',
              isCollapsed ? '' : 'scale-y-[-1]'
            )}
          />
        </button>
      </div>
      <Collapsible collapsed={isCollapsed}>
        <Response className="ml-6 grid border-l-4 border-gray-300 pl-3 text-gray-500">
          {reasoningText}
        </Response>
      </Collapsible>
    </motion.div>
  );
}

// TODO: use this method of calculating message duration once the server authoritative timestamps are accurate
// const getMessageDuration = (message: TaskMessage): number => {
//   if (!message.created_at || !message.updated_at) {
//     return 0;
//   }

//   const createdAt = new Date(message.created_at).getTime();
//   const updatedAt = new Date(message.updated_at).getTime();
//   const durationMs = updatedAt - createdAt;

//   const diffSec = durationMs / 1000;

//   // Convert to seconds and round up
//   return diffSec < 10 ? Math.round(diffSec * 10) / 10 : Math.round(diffSec);
// };

const calculateThinkingTime = (
  message: TaskMessage,
  nextBlockTimestamp: TaskMessage['created_at']
) => {
  // Need both user prompt and agent response to calculate thinking time
  if (!message.created_at || !nextBlockTimestamp) {
    return null;
  }

  // Convert ISO strings to Date objects and return the difference in seconds
  const promptDate = new Date(message.created_at);
  const responseDate = new Date(nextBlockTimestamp);
  const diffMs = responseDate.getTime() - promptDate.getTime();
  const diffSec = diffMs / 1000;

  // Round to nearest 10th of a second for times less than 10 seconds, otherwise round to nearest second
  return diffSec < 10 ? Math.round(diffSec * 10) / 10 : Math.round(diffSec);
};
