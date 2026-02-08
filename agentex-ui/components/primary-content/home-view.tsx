import { motion } from 'framer-motion';

import { AgentsList } from '@/components/agents-list/agents-list';
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
        <div className="mb-6 text-3xl font-bold">Agentex</div>
        <AgentsList agents={agents} isLoading={isLoading} />
        <div
          className={`flex items-center gap-2 ${
            agentName ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        >
          <button
            onClick={() => {
              updateParams({ [SearchParamKey.AGENT_NAME]: null });
              setLocalAgentName(undefined);
            }}
            className={`text-accent-foreground cursor-pointer text-xs transition-opacity duration-200 hover:underline`}
          >
            view all agents
          </button>
          <kbd
            className={`bg-muted text-muted-foreground pointer-events-none inline-flex h-4 items-center gap-1 rounded border px-1 font-mono text-[10px] font-medium opacity-100 select-none`}
          >
            esc
          </kbd>
        </div>
      </div>
    </motion.div>
  );
}
