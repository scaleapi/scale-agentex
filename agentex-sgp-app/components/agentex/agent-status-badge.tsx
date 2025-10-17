import { Badge } from '@/components/ui/badge';
import type { Agent } from 'agentex/resources';
import { cva } from 'class-variance-authority';

const variants = cva('', {
  variants: {
    status: {
      Building: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
      Pending: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
      Ready:
        'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
      Failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
      Unknown: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
    },
  },
});

type Props = {
  status: Agent['status'];
};

export function AgentStatusBadge({ status }: Props) {
  const nonNullStatus = status ?? 'Unknown';

  return (
    <Badge className={variants({ status: nonNullStatus })}>
      {nonNullStatus}
    </Badge>
  );
}
