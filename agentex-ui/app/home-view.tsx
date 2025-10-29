import { motion } from 'framer-motion';

import { AgentsList } from '@/components/agentex/agents-list';
import { useAgentexClient } from '@/components/providers/agentex-provider';
import { useAgents } from '@/hooks/use-agents';
import { useLocalStorageState } from '@/hooks/use-local-storage-state';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

export function HomeView() {
  const { agentName, updateParams } = useSafeSearchParams();
  const { agentexClient } = useAgentexClient();
  const { data: agents = [], isLoading } = useAgents(agentexClient);
  const [, setLocalAgentName] = useLocalStorageState<string | undefined>(
    'lastSelectedAgent',
    undefined
  );

  return (
    <motion.div
      key="home-view"
      className="flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
    >
      <div className="flex flex-col items-center justify-center px-4">
        <div className="mb-6 text-2xl font-bold">Agentex</div>
        <AgentsList agents={agents} isLoading={isLoading} />
        <button
          onClick={() => {
            updateParams({ [SearchParamKey.AGENT_NAME]: null });
            setLocalAgentName(undefined);
          }}
          className={`text-muted-foreground cursor-pointer text-xs transition-opacity duration-200 hover:underline ${
            agentName ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        >
          view all agents
        </button>
      </div>
    </motion.div>
  );
}
