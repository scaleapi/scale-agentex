import { useEffect, useRef } from 'react';

import Link from 'next/link';

import { Agent } from 'agentex/resources';
import { motion } from 'framer-motion';

import { AgentBadge } from '@/components/agents-list/agent-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';

type AgentsListProps = {
  agents: Agent[];
  isLoading?: boolean;
};

// Agents registered at build time (AGX1-308) have a row but no acp_url and are
// not routable. Deploy-time registration flips them to `Ready`. Hide these from
// the list so they don't clutter the deployed, routable agents. Typed as
// `string` because the `agentex` SDK's Agent.status union doesn't include it yet.
const BUILD_ONLY_STATUS: string = 'BuildOnly';

export function AgentsList({ agents, isLoading = false }: AgentsListProps) {
  const { agentName: selectedAgentName } = useSafeSearchParams();
  const hasMounted = useRef(false);

  useEffect(() => {
    hasMounted.current = true;
  }, []);

  const routableAgents = agents.filter(
    agent => agent.status !== BUILD_ONLY_STATUS
  );

  const displayedAgents = selectedAgentName
    ? routableAgents.filter(agent => agent.name === selectedAgentName)
    : routableAgents;

  if (isLoading) {
    return (
      <div className="mb-2 flex max-w-4xl flex-wrap items-center justify-center gap-2">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-9.5 w-32 rounded-full" />
        ))}
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={200}>
      <motion.div
        className="mb-2 flex max-h-[60vh] max-w-4xl flex-wrap items-center justify-center gap-2 overflow-y-auto"
        layout={hasMounted.current}
      >
        {displayedAgents.length > 0 ? (
          displayedAgents?.map(agent => (
            <AgentBadge key={agent.name} agent={agent} />
          ))
        ) : (
          <div className="flex items-center justify-center">
            <p className="text-muted-foreground text-xs">
              {'No agents found. '}
              <Link
                href="https://github.com/scaleapi/scale-agentex#getting-started"
                target="_blank"
                className="decoration-muted-foreground/50 hover:decoration-foreground underline underline-offset-2 transition-colors"
              >
                {'Learn how to create one'}
              </Link>
            </p>
          </div>
        )}
      </motion.div>
    </TooltipProvider>
  );
}
