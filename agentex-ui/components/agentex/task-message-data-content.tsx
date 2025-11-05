import { memo } from 'react';

import { cva } from 'class-variance-authority';

import { ExternalEventCallout } from '@/components/agentex/external-event-callout';
import { JsonViewer } from '@/components/agentex/json-viewer';
import type { JsonValue } from '@/lib/types';
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

type TaskMessageDataContentProps = {
  content: DataContent;
  key?: string | undefined;
};

function TaskMessageDataContentImpl({
  content,
  key,
}: TaskMessageDataContentProps) {
  const isExternalEvent =
    content.data &&
    typeof content.data === 'object' &&
    'type' in content.data &&
    content.data.type === 'external_event';

  if (
    isExternalEvent &&
    'event' in content.data &&
    'part_url' in content.data
  ) {
    return (
      <div className={cn(variants({ author: content.author }))}>
        <ExternalEventCallout
          key={key}
          event={String(content.data.event)}
          url={String(content.data.part_url)}
        />
      </div>
    );
  }

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

const TaskMessageDataContent = memo(TaskMessageDataContentImpl);

export { TaskMessageDataContent };
