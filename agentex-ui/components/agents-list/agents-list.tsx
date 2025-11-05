import { useEffect, useRef } from 'react';

import { Agent } from 'agentex/resources';
import { AnimatePresence, motion } from 'framer-motion';

import { AgentBadge } from '@/components/agents-list/agent-badge';
import { Skeleton } from '@/components/ui/skeleton';
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

  return (
    <motion.div
      className="mb-2 flex max-w-4xl flex-wrap items-center justify-center gap-2"
      layout={hasMounted.current}
    >
      {isLoading ? (
        <>
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-9.5 w-32 rounded-full" />
          ))}
        </>
      ) : (
        <AnimatePresence mode="sync">
          {displayedAgents?.map(agent => (
            <AgentBadge key={agent.name} agent={agent} />
          ))}
        </AnimatePresence>
      )}
    </motion.div>
  );
}
