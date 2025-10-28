import { memo, useMemo, useState } from 'react';

import { motion } from 'framer-motion';
import { ChevronDownIcon, Wrench } from 'lucide-react';

import { ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import { cn } from '@/lib/utils';

import { Collapsible } from '../ui/collapsible';
import { ShimmeringText } from '../ui/shimmering-text';

import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';

export type TaskMessageToolPairProps = {
  toolRequestMessage: TaskMessage & { content: ToolRequestContent };
  toolResponseMessage?:
    | (TaskMessage & { content: ToolResponseContent })
    | undefined;
};

function TaskMessageToolPairComponent({
  toolRequestMessage,
  toolResponseMessage,
}: TaskMessageToolPairProps) {
  const [isCollapsed, setIsCollapsed] = useState(true);

  // const state = useMemo(() => {
  //   const streamingStatus = toolResponseMessage?.streaming_status;
  //   if (streamingStatus === 'IN_PROGRESS') {
  //     return 'input-streaming';
  //   } else {
  //     try {
  //       const content = toolResponseMessage?.content.content;
  //       if (typeof content === 'string') {
  //         const parsed = JSON.parse(content);
  //         if (parsed.status === 'error') {
  //           return 'output-error';
  //         }
  //       }
  //     } catch {
  //       return 'output-available';
  //     }
  //     return 'output-available';
  //   }
  // }, [toolResponseMessage]);

  const reponseObject = useMemo(() => {
    const content = toolResponseMessage?.content.content;
    if (typeof content === 'string') {
      try {
        return JSON.parse(content);
      } catch {
        return content;
      }
    }
    return content;
  }, [toolResponseMessage]);

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
        <Wrench className="size-4" />
        <ShimmeringText
          enabled={!toolResponseMessage}
          text={
            !toolResponseMessage
              ? 'Using tool:  ' + toolRequestMessage.content.name
              : 'Used tool:  ' + toolRequestMessage.content.name
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
        <div className="ml-6 flex flex-col gap-4">
          <ToolInput input={toolRequestMessage.content.arguments} />
          <ToolOutput output={reponseObject} errorText={undefined} />
        </div>
      </Collapsible>
    </motion.div>
  );
}

const MemoizedTaskMessageToolPairComponent = memo(TaskMessageToolPairComponent);

export { MemoizedTaskMessageToolPairComponent, TaskMessageToolPairComponent };
