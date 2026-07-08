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
  // Whether the platform API is configured, so the account picker can fetch/switch accounts
  accountsEnabled: boolean;
  // Selected account id (from the `account_id` query param) + a setter that mirrors it
  // to the URL and updates the header the SDK sends.
  selectedAccountId: string | null;
  setSelectedAccountId: (id: string, replace?: boolean) => void;
}

const AgentexContext = createContext<AgentexContextValue | null>(null);

/**
 * Main provider. The SDK ALWAYS targets the same-origin BFF proxy (`/api/agentex`), which
 * forwards credentials server-side. The selected account travels as the
 * `x-selected-account-id` header, sourced from the `account_id` query param — no cookie
 * involved.
 */
export function AgentexProvider({
  children,
  sgpAppURL,
  accountsEnabled,
}: {
  children: ReactNode;
  sgpAppURL: string;
  accountsEnabled: boolean;
}) {
  const { sgpAccountID, updateParams } = useSafeSearchParams();

  // Synchronous source for the SDK's per-request header. Seeded from the URL and kept in
  // sync with it; setSelectedAccountId also sets it synchronously so a switch's refetch doesn't
  // race the (async) URL navigation.
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
          // An explicit switch (not the initial bootstrap, which passes replace) drops the
          // open task — it's account-scoped and won't resolve under the new account.
          ...(replace ? {} : { [SearchParamKey.TASK_ID]: null }),
        },
        replace
      );
    },
    [updateParams]
  );

  const agentexClient = useMemo(() => {
    // The SDK builds request URLs with `new URL()`, so the base must be ABSOLUTE. On the
    // server `window` is absent, but no request fires during the initial server render
    // (react-query fetches on the client); the client render recomputes an absolute URL.
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
