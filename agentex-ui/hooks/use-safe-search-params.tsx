import { useCallback, useMemo } from 'react';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';

export enum SearchParamKey {
  SGP_ACCOUNT_ID = 'account_id',
  TASK_ID = 'task_id',
  AGENT_NAME = 'agent_name',
}

type SearchParamUpdates = Partial<Record<SearchParamKey, string | null>>;

type SafeSearchParams = {
  sgpAccountID: string | null;
  taskID: string | null;
  agentName: string | null;
  updateParams: (updates: SearchParamUpdates, replace?: boolean) => void;
};

/**
 * This will suspend rendering. Be sure you put suspense boundary somewhere.
 */
export function useSafeSearchParams(): SafeSearchParams {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const sgpAccountID = searchParams.get(SearchParamKey.SGP_ACCOUNT_ID);
  const taskID = searchParams.get(SearchParamKey.TASK_ID);
  const agentName = searchParams.get(SearchParamKey.AGENT_NAME);

  const updateParams = useCallback(
    (updates: SearchParamUpdates, replace: boolean = false): void => {
      const params = new URLSearchParams(searchParams.toString());

      Object.entries(updates).forEach(([key, value]) => {
        const paramKey = key as SearchParamKey;
        if (value !== undefined) {
          if (value === null) {
            params.delete(paramKey);
          } else {
            params.set(paramKey, value);
          }
        }
      });

      if (replace) {
        router.replace(`${pathname}?${params.toString()}`);
      } else {
        router.push(`${pathname}?${params.toString()}`);
      }
    },
    [pathname, searchParams, router]
  );

  return useMemo(
    () => ({
      sgpAccountID: sgpAccountID || null,
      taskID: taskID || null,
      agentName: agentName || null,
      updateParams,
    }),
    [sgpAccountID, taskID, agentName, updateParams]
  );
}
