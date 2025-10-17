import { CodeBlock } from '@/components/ai-elements/code-block';
import { CopyButton } from '@/components/agentex/copy-button';
import type { DataContent } from 'agentex/resources';
import { cn } from '@/lib/utils';
import { cva } from 'class-variance-authority';
import { useMemo } from 'react';

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

function TaskMessageDataContentComponent({
  content,
  key,
}: TaskMessageDataContentComponentProps) {
  const dataString = useMemo(
    () => JSON.stringify(content.data, null, 2),
    [content.data]
  );
  return (
    <div className={cn(variants({ author: content.author }))}>
      <CodeBlock key={key} language="json" code={dataString}>
        <CopyButton content={dataString} />
      </CodeBlock>
    </div>
  );
}

export { TaskMessageDataContentComponent };
