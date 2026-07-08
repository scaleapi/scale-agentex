'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';

import AgentexSDK from 'agentex';

import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';

interface AgentexContextValue {
  agentexClient: AgentexSDK;
  sgpAppURL: string;
  authEnabled: boolean;
  // Platform API configured → the account picker can fetch/switch accounts.
  accountsEnabled: boolean;
  // Selected account (from the `account_id` param) + a setter that mirrors it to the URL.
  selectedAccountId: string | null;
  setSelectedAccountId: (id: string, replace?: boolean) => void;
}

const AgentexContext = createContext<AgentexContextValue | null>(null);

/**
 * The SDK always targets the same-origin BFF (`/api/agentex`), which attaches credentials
 * server-side. The selected account rides as `x-selected-account-id`, from the `account_id`
 * query param.
 */
export function AgentexProvider({
  children,
  sgpAppURL,
  authEnabled,
  accountsEnabled,
}: {
  children: ReactNode;
  sgpAppURL: string;
  authEnabled: boolean;
  accountsEnabled: boolean;
}) {
  const { sgpAccountID, updateParams } = useSafeSearchParams();

  // Synchronous source for the SDK header: setSelectedAccountId sets it before the (async)
  // URL navigation, so a switch's refetch doesn't race it.
  const selectedAccountIdRef = useRef<string | null>(sgpAccountID);
  useEffect(() => {
    selectedAccountIdRef.current = sgpAccountID;
  }, [sgpAccountID]);

  const setSelectedAccountId = useCallback(
    (id: string, replace = false) => {
      selectedAccountIdRef.current = id;
      updateParams(
        {
          [SearchParamKey.SGP_ACCOUNT_ID]: id,
          // An explicit switch (not bootstrap, which passes replace) drops the open task:
          // it's account-scoped and won't resolve under the new account.
          ...(replace ? {} : { [SearchParamKey.TASK_ID]: null }),
        },
        replace
      );
    },
    [updateParams]
  );

  const agentexClient = useMemo(() => {
    // The SDK builds URLs with `new URL()`, so the base must be absolute. `window` is absent
    // on the server, but no request fires during SSR; the client render recomputes it.
    const baseURL =
      typeof window !== 'undefined'
        ? `${window.location.origin}/api/agentex`
        : '/api/agentex';

    return new AgentexSDK({
      baseURL,
      fetchOptions: { credentials: 'include' },
      // Attach the selected account on every request (read from the ref — always current).
      fetch: (input, init) => {
        const headers = new Headers(init?.headers);
        if (selectedAccountIdRef.current) {
          headers.set('x-selected-account-id', selectedAccountIdRef.current);
        }
        return fetch(input, { ...init, headers });
      },
    });
  }, []);

  return (
    <AgentexContext.Provider
      value={{
        agentexClient,
        sgpAppURL,
        authEnabled,
        accountsEnabled,
        selectedAccountId: sgpAccountID,
        setSelectedAccountId,
      }}
    >
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
