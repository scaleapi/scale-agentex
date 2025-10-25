'use client';

import { type ReactNode } from 'react';

import { useAgentexClient } from '@/components/providers/agentex-provider';
import { useAgents } from '@/hooks/use-agents';
import { useSafeSearchParams } from '@/hooks/use-safe-search-params';
import { useTaskSubscription } from '@/hooks/use-task-subscription';

/**
 * Task provider component
 * Bootstraps real-time SSE subscription for a specific task
 *
 * TODO: Debug why subscribeTaskState doesn't receive events from agentRPCWithStreaming
 * Currently both streams are active (redundant) but only RPC stream updates UI
 */
export function TaskProvider({
  taskId,
  children,
  fallback,
}: {
  taskId: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { agentexClient } = useAgentexClient();
  const { agentName } = useSafeSearchParams();

  const { data: agents = [] } = useAgents(agentexClient);
  const agent = agents.find(a => a.name === agentName);

  // SSE subscription - connects on mount, should receive all task events
  // Currently only receives initial load, not new events from message/send
  useTaskSubscription({
    agentexClient,
    taskId,
    enabled: !!taskId && agent?.acp_type === 'agentic',
  });

  if (!taskId && fallback) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
