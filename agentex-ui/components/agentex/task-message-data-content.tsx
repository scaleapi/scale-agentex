import { memo } from 'react';

import { cva } from 'class-variance-authority';

import { JsonViewer, type JsonValue } from '@/components/agentex/json-viewer';
import { cn } from '@/lib/utils';

import type { DataContent } from 'agentex/resources';

const variants = cva('', {
  variants: {
    author: {
      user: 'ml-auto w-fit max-w-[80%]',
      agent: '',
    },
  },
});

type TaskMessageDataContentComponentProps = {
  content: DataContent;
  key?: string | undefined;
};

function TaskMessageDataContentComponentImpl({
  content,
  key,
}: TaskMessageDataContentComponentProps) {
  return (
    <div className={cn(variants({ author: content.author }))}>
      <JsonViewer
        key={key}
        data={content.data as JsonValue}
        defaultOpenDepth={1}
      />
    </div>
  );
}

const TaskMessageDataContentComponent = memo(
  TaskMessageDataContentComponentImpl
);

export { TaskMessageDataContentComponent };
