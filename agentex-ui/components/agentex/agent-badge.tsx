import { memo } from 'react';

import { motion } from 'framer-motion';

import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

import type { Agent } from 'agentex/resources';

type AgentBadgeProps = {
  agent: Agent;
};

function AgentBadgeImpl({ agent }: AgentBadgeProps) {
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

const AgentBadge = memo(AgentBadgeImpl);

export { AgentBadge };
