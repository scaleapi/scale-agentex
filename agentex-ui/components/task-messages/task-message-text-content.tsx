import { memo } from 'react';

import { cva } from 'class-variance-authority';

import { MarkdownResponse } from '@/components/task-messages/markdown-response';
import { TaskMessageExternalEvent } from '@/components/task-messages/task-message-external-event';
import { parseProcurementEventFromText } from '@/lib/procurement-utils';
import { cn } from '@/lib/utils';

import type { TextContent } from 'agentex/resources';

const variants = cva('', {
  variants: {
    author: {
      user: 'rounded-md shadow-sm bg-muted text-muted-foreground ml-auto w-fit max-w-[80%] p-4',
      agent: '',
    },
  },
});

type TaskMessageTextContentProps = {
  content: TextContent;
  key?: string | undefined;
};

function TaskMessageTextContentImpl({
  content,
  key,
}: TaskMessageTextContentProps) {
  if (content.author === 'user') {
    const eventData = parseProcurementEventFromText(content.content);
    if (eventData) {
      return <TaskMessageExternalEvent key={key} event={eventData} />;
    }
  }

  return (
    <div className={cn(variants({ author: content.author }))}>
      <MarkdownResponse key={key}>{content.content}</MarkdownResponse>
    </div>
  );
}

const TaskMessageTextContent = memo(TaskMessageTextContentImpl);

export { TaskMessageTextContent };
