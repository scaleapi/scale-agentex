import { memo, useMemo, useState } from 'react';

import { motion } from 'framer-motion';
import { ChevronDownIcon, Wrench, XCircleIcon } from 'lucide-react';

import { JsonViewer } from '@/components/agentex/json-viewer';
import { Collapsible } from '@/components/ui/collapsible';
import { ShimmeringText } from '@/components/ui/shimmering-text';
import type { JsonValue } from '@/lib/types';
import { cn } from '@/lib/utils';

import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';

type TaskMessageToolHeaderAndJsonProps = {
  title: string;
  data: JsonValue;
};

function TaskMessageToolHeaderAndJsonComponent({
  title,
  data,
}: TaskMessageToolHeaderAndJsonProps) {
  return (
    <div className="space-y-2 overflow-hidden">
      <h4 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {title}
      </h4>
      <div className="bg-muted/50 rounded-md">
        <JsonViewer
          data={data}
          defaultOpenDepth={1}
          className="bg-background max-h-[200px] overflow-y-auto"
        />
      </div>
    </div>
  );
}

type TaskMessageToolPairProps = {
  toolRequestMessage: TaskMessage & { content: ToolRequestContent };
  toolResponseMessage?:
    | (TaskMessage & { content: ToolResponseContent })
    | undefined;
};

function TaskMessageToolPairComponentImpl({
  toolRequestMessage,
  toolResponseMessage,
}: TaskMessageToolPairProps) {
  const [isCollapsed, setIsCollapsed] = useState(true);

  const responseObject = useMemo<JsonValue>(() => {
    const content = toolResponseMessage?.content.content;
    if (typeof content === 'string') {
      try {
        return JSON.parse(content) as JsonValue;
      } catch {
        return content as JsonValue;
      }
    }
    return content as JsonValue;
  }, [toolResponseMessage]);

  const isError = useMemo<boolean>(
    () =>
      typeof responseObject === 'object' &&
      responseObject !== null &&
      'status' in responseObject &&
      typeof responseObject.status === 'string' &&
      responseObject.status.toLowerCase() === 'error',
    [responseObject]
  );

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
        {isError && <XCircleIcon className="size-4 text-red-600" />}
        <ChevronDownIcon
          className={cn(
            'size-4 transition-transform duration-500',
            isCollapsed ? '' : 'scale-y-[-1]'
          )}
        />
      </button>
      <Collapsible collapsed={isCollapsed}>
        <div className="ml-6 flex flex-col gap-4">
          <TaskMessageToolHeaderAndJsonComponent
            title="Parameters"
            data={toolRequestMessage.content.arguments as JsonValue}
          />
          <TaskMessageToolHeaderAndJsonComponent
            title="Result"
            data={responseObject}
          />
        </div>
      </Collapsible>
    </motion.div>
  );
}

const MemoizedTaskMessageToolPairComponent = memo(
  TaskMessageToolPairComponentImpl
);

export { MemoizedTaskMessageToolPairComponent };
