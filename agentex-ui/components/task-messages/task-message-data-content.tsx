import { memo } from 'react';

import { cva } from 'class-variance-authority';

import { TaskMessageExternalEvent } from '@/components/task-messages/task-message-external-event';
import { JsonViewer } from '@/components/ui/json-viewer';
import { isProcurementEventData } from '@/lib/procurement-utils';
import type { JsonValue } from '@/lib/types';
import { cn } from '@/lib/utils';

import type { DataContent } from 'agentex/resources';

const variants = cva('', {
  variants: {
    author: {
      user: 'ml-auto w-fit max-w-[80%]',
      procurement_event: '',
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
  return (
    <div
      className={cn(
        variants({
          author: isProcurementEventData(content.data)
            ? 'procurement_event'
            : content.author,
        })
      )}
    >
      {isProcurementEventData(content.data) ? (
        <TaskMessageExternalEvent key={key} event={content.data} />
      ) : (
        <JsonViewer
          key={key}
          data={content.data as JsonValue}
          defaultOpenDepth={1}
        />
      )}
    </div>
  );
}

const TaskMessageDataContent = memo(TaskMessageDataContentImpl);

export { TaskMessageDataContent };
