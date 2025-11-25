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

export function AgentsList({ agents, isLoading = false }: AgentsListProps) {
  const { agentName: selectedAgentName } = useSafeSearchParams();
  const hasMounted = useRef(false);

  useEffect(() => {
    hasMounted.current = true;
  }, []);

  const displayedAgents = selectedAgentName
    ? agents.filter(agent => agent.name === selectedAgentName)
    : agents;

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
        className="mb-2 flex max-w-4xl flex-wrap items-center justify-center gap-2"
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
