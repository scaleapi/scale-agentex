import { motion } from 'framer-motion';

import { AgentsList } from '@/components/agentex/agents-list';
import { ProjectCreationForm } from '@/components/agentex/project/project-creation-form';
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

  const showProjectForm = agentName === 'example-tutorial';

  return (
    <motion.div
      key="home-view"
      className="flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
    >
      <div className="flex w-full max-w-4xl flex-col items-center justify-center px-4 sm:px-6 md:px-8">
        <div className="mb-6 text-2xl font-bold">Agentex</div>
        <AgentsList agents={agents} isLoading={isLoading} />
        <button
          onClick={() => {
            updateParams({ [SearchParamKey.AGENT_NAME]: null });
            setLocalAgentName(undefined);
          }}
          className={`text-accent-foreground cursor-pointer text-xs transition-opacity duration-200 hover:underline ${
            agentName ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        >
          view all agents
        </button>
        {showProjectForm && (
          <div className="mt-8 w-full max-w-2xl">
            <ProjectCreationForm />
          </div>
        )}
      </div>
    </motion.div>
  );
}
