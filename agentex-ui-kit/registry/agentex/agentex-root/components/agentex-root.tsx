import {
  AgentexRootStore,
  AgentexRootStoreContext,
  createAgentexRootStore,
} from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import type AgentexSDK from "agentex";
import { useEffect, useRef, useState } from "react";

type AgentexRootProps = {
  agentexClient: AgentexSDK;
  fallback?: React.ReactNode;
  children?: React.ReactNode;
  onError?: ((error: unknown) => void) | undefined;
};

function AgentexRoot({
  children,
  fallback,
  agentexClient,
  onError,
}: AgentexRootProps) {
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
      agentexClient.agents.list(
        undefined, // query
        { signal: abortController.signal }
      ),
      agentexClient.tasks.list(
        undefined, // query
        { signal: abortController.signal }
      ),
    ]).then(
      ([agents, tasks]) => {
        if (abortController.signal.aborted) return;
        setStore(
          createAgentexRootStore({
            agentexClient,
            agents,
            tasks,
          })
        );
      },
      (error) => {
        if (abortController.signal.aborted) {
          return;
        }
        if (onErrorRef.current !== undefined) {
          onErrorRef.current(error);
          return;
        }
        throw error;
      }
    );

    return () => {
      abortController.abort();
    };
  }, [agentexClient, setStore]);

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

export { AgentexRoot };
