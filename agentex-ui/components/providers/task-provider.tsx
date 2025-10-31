'use client';

import { type ReactNode } from 'react';

import { useAgentexClient } from '@/components/providers/agentex-provider';
import { useAgents } from '@/hooks/use-agents';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useTaskSubscription } from '@/hooks/use-task-subscription';

export function TaskProvider({
  taskId,
  children,
}: {
  taskId: string;
  children: ReactNode;
}) {
  const { agentexClient } = useAgentexClient();
  const { agentName } = useSafeSearchParams();

  const { data: agents = [] } = useAgents(agentexClient);
  const agent = agents.find(a => a.name === agentName);

  useTaskSubscription({
    agentexClient,
    taskId,
    agentName: agentName || '',
    enabled: !!taskId && (agent?.acp_type === 'agentic' || !agentName),
  });

  return <>{children}</>;
}
