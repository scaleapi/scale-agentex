import { AgentStatusBadge } from '@/components/agentex/agent-status-badge';
import { Skeleton } from '@/components/ui/skeleton';
import type { Agent } from 'agentex/resources';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { memo, Suspense } from 'react';

export type AgentLinkProps = {
  agent: Agent;
};

function AgentLinkImpl({ agent }: AgentLinkProps) {
  const searchParams = useSearchParams();

  return (
    <div className="flex flex-col items-stretch gap-2 rounded-md border p-4">
      <Link
        className="hover:bg-accent hover:text-accent-foreground rounded-md px-4 py-2"
        prefetch={false}
        href={`/agent/${agent.name}?${searchParams.toString()}`}
      >
        <h2>{agent.name}</h2>
      </Link>
      <div className="flex flex-col divide-y-2 gap-2 px-4">
        <p className="p-1">{agent.description}</p>

        <div className="flex justify-between items-baseline-last">
          <AgentStatusBadge status={agent.status} />{' '}
          <span>{agent.status_reason}</span>
        </div>
      </div>
    </div>
  );
}

function SuspendedAgentLink({ ...props }: AgentLinkProps) {
  return (
    <Suspense fallback={<Skeleton className="w-full h-25 animate-pulse" />}>
      <AgentLinkImpl {...props} />
    </Suspense>
  );
}

export const AgentLink = memo(SuspendedAgentLink);
