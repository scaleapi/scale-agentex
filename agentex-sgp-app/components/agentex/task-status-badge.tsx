import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { Task } from 'agentex/resources';
import { cva } from 'class-variance-authority';

const variants = cva('', {
  variants: {
    status: {
      CANCELED: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
      COMPLETED:
        'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
      FAILED: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
      RUNNING: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
      TERMINATED:
        'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
      TIMED_OUT:
        'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
      UNKNOWN: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
    },
    size: {
      sm: 'text-xs py-1 px-2',
      lg: 'text-sm py-2 px-4',
    },
  },
});

type Props = {
  status: Task['status'];
  className?: string;
  size?: 'sm' | 'lg';
};

export function TaskStatusBadge({ status, className, size }: Props) {
  const nonNullStatus = status ?? 'UNKNOWN';

  return (
    <Badge className={cn(variants({ status: nonNullStatus, size, className }))}>
      {nonNullStatus}
    </Badge>
  );
}
