'use client';

import {
  AgentexRootStore,
  AgentexRootStoreContext,
  createAgentexRootStore,
} from '@/hooks/use-agentex-root-store';
import { useAppConfig } from '@/hooks/use-app-config';
import { useRedirectClientToLoginRef } from '@/hooks/use-redirect-client-to-login';
import AgentexSDK, { AuthenticationError } from 'agentex';
import { useEffect, useRef, useState } from 'react';

export type AgentexNoAgentRootProps = {
  children?: React.ReactNode;
  fallback?: React.ReactNode;
  onError: (error: unknown) => void;
};

export function AgentexNoAgentRoot({
  children,
  fallback,
  onError,
}: AgentexNoAgentRootProps) {
  const { agentexAPIBaseURL } = useAppConfig();
  const [store, setStore] = useState<AgentexRootStore | null>(null);

  const onErrorRef = useRef<typeof onError>(onError);
  // keep onErrorRef in sync
  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  const redirectToLoginRef = useRedirectClientToLoginRef();

  // bootstrap
  // Construct a client from public runtime env and seed the root store with
  // the agent list. In no-agent mode we don't prefetch tasks or messages;
  // single-agent mode handles message caching when a task context exists.
  useEffect(() => {
    const abortController = new AbortController();

    setStore(null);
    const agentexClient = new AgentexSDK({
      baseURL: agentexAPIBaseURL,
    });

    agentexClient.agents
      .list(undefined, {
        signal: abortController.signal,
      })
      .then(
        (agents) => {
          if (abortController.signal.aborted) return;
          setStore(
            createAgentexRootStore({
              agentexClient,
              agents,
              tasks: [],
            })
          );
        },
        (error) => {
          if (abortController.signal.aborted) {
            return;
          }

          if (error instanceof AuthenticationError) {
            redirectToLoginRef.current();
          }

          onErrorRef.current(error);
        }
      );

    return () => {
      abortController.abort();
    };
  }, [setStore]);

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
