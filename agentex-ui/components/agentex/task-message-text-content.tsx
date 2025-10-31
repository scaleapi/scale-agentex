import { memo } from 'react';

import { cva } from 'class-variance-authority';

import { MarkdownResponse } from '@/components/agentex/markdown-response';
import { cn } from '@/lib/utils';

import type { TextContent } from 'agentex/resources';

const variants = cva('', {
  variants: {
    author: {
      user: 'rounded-md bg-muted text-muted-foreground ml-auto w-fit max-w-[80%] p-4',
      agent: '',
    },
  },
});

type TaskMessageTextContentComponentProps = {
  content: TextContent;
  key?: string | undefined;
};

function TaskMessageTextContentComponentImpl({
  content,
  key,
}: TaskMessageTextContentComponentProps) {
  return (
    <div className={cn(variants({ author: content.author }))}>
      <MarkdownResponse key={key}>{content.content}</MarkdownResponse>
    </div>
  );
}

const TaskMessageTextContentComponent = memo(
  TaskMessageTextContentComponentImpl
);

export { TaskMessageTextContentComponent };
