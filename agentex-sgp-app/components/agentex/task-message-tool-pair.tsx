import type {
  TaskMessage,
  ToolRequestContent,
  ToolResponseContent,
} from 'agentex/resources';
import { memo, useMemo } from 'react';

import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from '@/components/ai-elements/tool';

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
  const state = useMemo(() => {
    const streamingStatus = toolResponseMessage?.streaming_status;
    if (streamingStatus === 'IN_PROGRESS') {
      return 'input-streaming';
    } else {
      try {
        const content = toolResponseMessage?.content.content;
        if (typeof content === 'string') {
          const parsed = JSON.parse(content);
          if (parsed.status === 'error') {
            return 'output-error';
          }
        }
      } catch {
        return 'output-available';
      }
      return 'output-available';
    }
  }, [toolResponseMessage]);

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
    <Tool>
      <ToolHeader
        title={toolRequestMessage.content.name}
        type={`tool-${toolRequestMessage.content.name}`}
        state={state}
      />
      <ToolContent>
        <ToolInput input={toolRequestMessage.content.arguments} />
        <ToolOutput output={reponseObject} errorText={undefined} />
      </ToolContent>
    </Tool>
  );
}

const MemoizedTaskMessageToolPairComponent = memo(TaskMessageToolPairComponent);

export { TaskMessageToolPairComponent, MemoizedTaskMessageToolPairComponent };
