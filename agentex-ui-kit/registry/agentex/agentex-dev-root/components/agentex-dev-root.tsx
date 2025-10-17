"use client";

import {
  AgentexDevRootSetupStore,
  AgentexDevRootSetupStoreContext,
  createAgentexDevRootSetupStore,
  useAgentexDevRootSetupStore,
} from "@/registry/agentex/agentex-dev-root/hooks/use-agentex-dev-root-setup";
import { AgentexRoot } from "@/registry/agentex/agentex-root/components/agentex-root";
import { useEffect, useRef, useState } from "react";

type AgentexDevRootProps = {
  children?: React.ReactNode;
  fallback?: React.ReactNode;
  onError?: ((error: unknown) => void) | undefined;
};

/**
 * Implementation for AgentexDevRoot after environment variables have been loaded.
 */
function AgentexDevRootImpl({
  children,
  fallback,
  onError,
}: AgentexDevRootProps) {
  const client = useAgentexDevRootSetupStore((s) => s.client);

  return (
    <AgentexRoot fallback={fallback} agentexClient={client} onError={onError}>
      {children}
    </AgentexRoot>
  );
}

/**
 * Shared Context for a single Agentex app. This is used as a replacement for AgentexRoot for development purposes.
 */
function AgentexDevRoot(props: AgentexDevRootProps) {
  const onErrorRef = useRef(props.onError);
  useEffect(() => {
    onErrorRef.current = props.onError;
  }, [props.onError]);

  const [store, setStore] = useState<AgentexDevRootSetupStore>();

  // bootstrap
  useEffect(() => {
    setStore(
      createAgentexDevRootSetupStore(
        {
          storageKey: "agentex-dev-root",
        },
        window.location
      )
    );
  }, [setStore]);

  if (!store) {
    return <div>Loading dev root...</div>;
  }

  return (
    <AgentexDevRootSetupStoreContext.Provider value={store}>
      <AgentexDevRootImpl {...props} />
    </AgentexDevRootSetupStoreContext.Provider>
  );
}

export { AgentexDevRoot };
