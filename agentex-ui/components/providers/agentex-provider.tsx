'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';

import AgentexSDK from 'agentex';

interface AgentexContextValue {
  agentexClient: AgentexSDK;
  sgpAppURL: string;
}

const AgentexContext = createContext<AgentexContextValue | null>(null);

/**
 * Main provider for Agentex application
 * Provides the Agentex SDK client and app configuration to all child components
 */
export function AgentexProvider({
  children,
  agentexAPIBaseURL,
  sgpAppURL,
}: {
  children: ReactNode;
  agentexAPIBaseURL: string;
  sgpAppURL: string;
}) {
  const agentexClient = useMemo(
    () =>
      new AgentexSDK({
        baseURL: agentexAPIBaseURL,
        fetch: (input: RequestInfo | URL, init?: RequestInit) => {
          return fetch(input, {
            ...init,
            credentials: 'include',
          });
        },
      }),
    [agentexAPIBaseURL]
  );

  return (
    <AgentexContext.Provider value={{ agentexClient, sgpAppURL }}>
      {children}
    </AgentexContext.Provider>
  );
}

export function useAgentexClient() {
  const context = useContext(AgentexContext);
  if (!context) {
    throw new Error('useAgentexClient must be used within AgentexProvider');
  }
  return context;
}
