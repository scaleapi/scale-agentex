'use client';

import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {cn} from '@/lib/utils';
import {cva} from 'class-variance-authority';
import {CheckCircle, ChevronDown, ChevronRight, Circle, Wrench} from 'lucide-react';
import {useState} from 'react';
import {LargeTextContent} from './large-text-content';

const rootVariants = cva(
  [
    'w-full max-w-full overflow-hidden flex flex-col justify-between p-0', // sizing
    'transition-colors rounded-md border-l-4', // misc
    'text-gray-800 border-gray-200 bg-white shadow-none', // color
    'dark:bg-gray-800 dark:text-gray-200 dark:border-gray-700', // color (dark)
  ].join(' '),
  {
    variants: {
      activityStatus: {
        static: '',
        active: 'border-l-blue-500 animate-pulse',
      },
    },
    defaultVariants: {
      activityStatus: 'static',
    },
  }
);

const iconVariants = cva('h-4 w-4', {
  variants: {
    variant: {
      request: 'text-blue-500',
      response: '',
    },
    activityStatus: {
      static: '',
      active: '',
    },
  },
  compoundVariants: [
    {
      variant: 'response',
      activityStatus: 'static',
      className: 'text-green-500',
    },
    {
      variant: 'response',
      activityStatus: 'active',
      className: 'text-blue-500',
    },
  ],
  defaultVariants: {
    activityStatus: 'static',
  },
});

type ToolMessageCardHeaderProps = {
  name: string;
  variant: 'request' | 'response';
  activityStatus?: 'static' | 'active';
  className?: string;
  isExpanded?: boolean;
  onTrigger: () => void;
};

function ToolMessageCardHeader({
  name,
  variant,
  activityStatus,
  className,
  isExpanded,
  onTrigger,
}: ToolMessageCardHeaderProps) {
  return (
    <CardHeader
      className={cn(
        'flex cursor-pointer flex-row items-center justify-between gap-2 space-y-0 p-4 hover:bg-gray-50 dark:hover:bg-gray-700',
        className
      )}
      onClick={onTrigger}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onTrigger();
        }
      }}
    >
      <div className="flex items-center gap-2">
        {variant === 'request' ? (
          <Wrench className={cn(iconVariants({variant}))} />
        ) : activityStatus !== 'active' ? (
          <CheckCircle
            className={cn(
              iconVariants({
                variant: variant satisfies 'response',
                activityStatus: activityStatus satisfies 'static' | undefined,
              })
            )}
          />
        ) : (
          <Circle
            className={cn(
              iconVariants({
                variant: variant satisfies 'response',
                activityStatus,
              })
            )}
          />
        )}
        <CardTitle className="text-sm font-normal">
          {variant === 'request' ? `Using tool: ${name}` : `Tool response: ${name}`}
        </CardTitle>
      </div>
      {isExpanded ? (
        <ChevronDown className="h-4 w-4" />
      ) : (
        <ChevronRight className="h-4 w-4" />
      )}
    </CardHeader>
  );
}

type ToolMessageCardContentProps = {
  content: unknown;
  className?: string;
};

function ToolMessageCardContent({content, className}: ToolMessageCardContentProps) {
  return (
    <CardContent className={className}>
      <LargeTextContent content={content} />
    </CardContent>
  );
}

type ToolMessageCardProps = {
  name: string;
  content: unknown;
  variant: 'request' | 'response';
  activityStatus?: 'static' | 'active';
  className?: string;
};

function ToolMessageCard({
  name,
  content,
  variant,
  activityStatus,
  className,
}: ToolMessageCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <Card
      onClick={() => setIsExpanded(!isExpanded)}
      className={cn(rootVariants({activityStatus, className}))}
    >
      <ToolMessageCardHeader
        name={name}
        variant={variant}
        activityStatus={activityStatus}
        isExpanded={isExpanded}
        onTrigger={() => setIsExpanded(!isExpanded)}
      />

      {isExpanded && (
        <ToolMessageCardContent content={content} className="mt-2 px-4 pb-4" />
      )}
    </Card>
  );
}

export {ToolMessageCard, ToolMessageCardContent, ToolMessageCardHeader};
