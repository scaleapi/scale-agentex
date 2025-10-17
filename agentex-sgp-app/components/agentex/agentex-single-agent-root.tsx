'use client';

import {
  AgentexRootStore,
  AgentexRootStoreContext,
  createAgentexRootStore,
} from '@/hooks/use-agentex-root-store';
import { useRedirectClientToLoginRef } from '@/hooks/use-redirect-client-to-login';
import { cacheFirstMessageForTasks } from '@/lib/task-message-cache';
import AgentexSDK, { AuthenticationError } from 'agentex';
import type { Agent } from 'agentex/resources';
import { useEffect, useState } from 'react';

type AgentexSingleAgentRootProps = {
  agentexClient: AgentexSDK;
  children?: React.ReactNode;
  agentName: Agent['name'];
};

function AgentexSingleAgentRoot({
  agentexClient,
  children,
  agentName,
}: AgentexSingleAgentRootProps) {
  const [store, setStore] = useState<AgentexRootStore | null>(null);
  const redirectToLoginRef = useRedirectClientToLoginRef();

  // bootstrap
  useEffect(() => {
    const abortController = new AbortController();

    setStore(null);

    Promise.all([
      agentexClient.agents.retrieveByName(agentName, {
        signal: abortController.signal,
      }),
      agentexClient.tasks.list(
        { agent_name: agentName },
        { signal: abortController.signal }
      ),
    ]).then(
      ([agent, tasks]) => {
        if (abortController.signal.aborted) return;
        const store = createAgentexRootStore({
          agentexClient,
          agents: [agent],
          tasks,
        });

        setStore(store);

        // Seed the cross-task message cache with the first message per task.
        // `AgentexTask` will keep the cache in sync for any task that is opened.
        cacheFirstMessageForTasks(store, abortController.signal).catch(
          (error) => {
            if (abortController.signal.aborted) {
              return;
            }
            if (error instanceof AuthenticationError) {
              redirectToLoginRef.current();
              return;
            }
            // Let Next.js error boundary handle the error
            throw error;
          }
        );
      },
      (error) => {
        if (abortController.signal.aborted) {
          return;
        }
        if (error instanceof AuthenticationError) {
          redirectToLoginRef.current();
          return;
        }
        // Let Next.js error boundary handle the error
        throw error;
      }
    );

    return () => {
      abortController.abort();
    };
  }, [setStore, agentexClient, agentName, redirectToLoginRef]);

  // Show nothing while loading - Next.js loading.tsx will handle this
  if (store === null) {
    return null;
  }

  // render
  return (
    <AgentexRootStoreContext.Provider value={store}>
      {children}
    </AgentexRootStoreContext.Provider>
  );
}

export { AgentexSingleAgentRoot };
