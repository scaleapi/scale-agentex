import { useAgentexRootStore } from '@/hooks/use-agentex-root-store';
import { A } from '@mobily/ts-belt';
import { AgentLink } from './agent-link';

export function AgentsList() {
  const allAgents = useAgentexRootStore((store) => store.agents);
  const agents = A.uniqBy(allAgents, (agent) => agent.name);

  return (
    <div className="flex flex-col gap-8">
      {agents.map((agent) => (
        <AgentLink key={agent.name} agent={agent} />
      ))}
    </div>
  );
}
