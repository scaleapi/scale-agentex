import { cva } from 'class-variance-authority';

import { Response } from '@/components/ai-elements/response';
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

function TaskMessageTextContentComponent({
  content,
  key,
}: TaskMessageTextContentComponentProps) {
  return (
    <div className={cn(variants({ author: content.author }))}>
      <Response key={key}>{content.content}</Response>
    </div>
  );
}

export { TaskMessageTextContentComponent };
