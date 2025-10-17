"use client";

import {
  AgentexRootStore,
  AgentexRootStoreContext,
  createAgentexRootStore,
} from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import AgentexSDK from "agentex";
import type { Agent } from "agentex/resources";
import { useEffect, useRef, useState } from "react";

type AgentexSingleAgentRootProps = {
  agentexClient: AgentexSDK;
  children?: React.ReactNode;
  fallback?: React.ReactNode;
  onError: (error: unknown) => void;
  agentName: Agent["name"];
};

function AgentexSingleAgentRoot({
  agentexClient,
  children,
  fallback,
  onError,
  agentName,
}: AgentexSingleAgentRootProps) {
  const [store, setStore] = useState<AgentexRootStore | null>(null);

  const onErrorRef = useRef<typeof onError>(onError);
  // keep onErrorRef in sync
  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

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
      },
      (error) => {
        if (abortController.signal.aborted) {
          return;
        }

        onErrorRef.current(error);
      }
    );

    return () => {
      abortController.abort();
    };
  }, [setStore, agentexClient, agentName]);

  // loading
  if (store === null) {
    return <>{fallback}</>;
  }

  // render
  return (
    <AgentexRootStoreContext.Provider value={store}>
      {children}
    </AgentexRootStoreContext.Provider>
  );
}

export { AgentexSingleAgentRoot };
