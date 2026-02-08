import { memo } from 'react';

import { motion } from 'framer-motion';

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
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

  const isDisabled = agent.status !== 'Ready';

  const handleClick = () => {
    if (isDisabled) return;

    if (isSelected) {
      updateParams({ [SearchParamKey.AGENT_NAME]: null });
      setLocalAgentName(undefined);
    } else {
      updateParams({ [SearchParamKey.AGENT_NAME]: agent.name });
      setLocalAgentName(agent.name);
    }
  };

  const button = (
    <motion.button
      layout
      onClick={handleClick}
      disabled={isDisabled}
      className={`relative overflow-hidden rounded-full px-4 py-2 text-sm font-medium ${
        isDisabled
          ? 'bg-muted scale-95 cursor-not-allowed border opacity-50 shadow-xs'
          : isSelected
            ? 'border-primary-foreground bg-primary text-primary-foreground cursor-pointer border shadow-md'
            : 'cursor-pointer border shadow-xs'
      } `}
      initial={isSelected ? false : { opacity: 0 }}
      animate={{
        opacity: isDisabled ? 0.5 : 1,
        scale: 1,
        transition: {
          delay: isSelected ? 0 : 0.2,
        },
      }}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      {...(!isDisabled && { whileHover: { scale: 1.05 } })}
      {...(!isDisabled && { whileTap: { scale: 0.95 } })}
      transition={{
        type: 'spring',
        stiffness: 500,
        damping: 40,
      }}
    >
      {agent.name}
    </motion.button>
  );

  if (isDisabled) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent>
          <p>
            Agent status is <span className="font-bold">{agent.status}</span>
          </p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return button;
}

const AgentBadge = memo(AgentBadgeImpl);

export { AgentBadge };
