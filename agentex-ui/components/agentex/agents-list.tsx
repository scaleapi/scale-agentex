import { useEffect, useRef } from 'react';

import { Agent } from 'agentex/resources';
import { AnimatePresence, motion } from 'framer-motion';

import { Skeleton } from '@/components/ui/skeleton';
import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

export type AgentsListProps = {
  agents: Agent[];
  isLoading?: boolean;
};

export function AgentsList({ agents, isLoading = false }: AgentsListProps) {
  const { agentName: selectedAgentName } = useSafeSearchParams();
  const hasMounted = useRef(false);

  useEffect(() => {
    hasMounted.current = true;
  }, []);

  // Filter agents: show only selected agent if one is selected, otherwise show all
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

interface AgentBadgeProps {
  agent: Agent;
}

function AgentBadge({ agent }: AgentBadgeProps) {
  const { agentName, updateParams } = useSafeSearchParams();
  const [, setLocalAgentName] = useLocalStorageState<string | undefined>(
    'lastSelectedAgent',
    undefined
  );
  const isSelected = agentName === agent.name;

  const handleClick = () => {
    if (isSelected) {
      updateParams({ [SearchParamKey.AGENT_NAME]: null });
      setLocalAgentName(undefined);
    } else {
      updateParams({ [SearchParamKey.AGENT_NAME]: agent.name });
      setLocalAgentName(agent.name);
    }
  };

  return (
    <motion.button
      layout
      onClick={handleClick}
      className={`relative cursor-pointer overflow-hidden rounded-full px-4 py-2 text-sm font-medium ${
        isSelected
          ? 'bg-primary text-primary-foreground border-primary-foreground border'
          : 'border-border border'
      } `}
      initial={isSelected ? false : { opacity: 0 }}
      animate={{
        opacity: 1,
        scale: 1,
        transition: {
          delay: isSelected ? 0 : 0.2,
        },
      }}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      transition={{
        type: 'spring',
        stiffness: 500,
        damping: 40,
      }}
    >
      {agent.name}
    </motion.button>
  );
}
