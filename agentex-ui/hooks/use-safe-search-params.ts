import { useCallback, useMemo } from 'react';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';

export enum SearchParamKey {
  SGP_ACCOUNT_ID = 'account_id',
  TASK_ID = 'task_id',
  AGENT_NAME = 'agent_name',
  VIEW = 'view',
  SCHEDULE_SCOPE = 'schedule_scope',
}

type SearchParamUpdates = Partial<Record<SearchParamKey, string | null>>;

export enum AppView {
  SCHEDULED_TASKS = 'scheduled_tasks',
}

export enum ScheduleScope {
  CURRENT = 'current',
  ALL = 'all',
}

type SafeSearchParams = {
  sgpAccountID: string | null;
  taskID: string | null;
  agentName: string | null;
  view: AppView | null;
  scheduleScope: ScheduleScope;
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
  const viewParam = searchParams.get(SearchParamKey.VIEW);
  const scheduleScopeParam = searchParams.get(SearchParamKey.SCHEDULE_SCOPE);
  const view =
    viewParam === AppView.SCHEDULED_TASKS ? AppView.SCHEDULED_TASKS : null;
  const scheduleScope =
    scheduleScopeParam === ScheduleScope.ALL
      ? ScheduleScope.ALL
      : ScheduleScope.CURRENT;

  const updateParams = useCallback(
    (updates: SearchParamUpdates, replace: boolean = false): void => {
      // Merge against the live URL, not the `searchParams` snapshot: the snapshot lags a
      // render behind router navigations, so concurrent updates would clobber each other.
      const live =
        typeof window !== 'undefined'
          ? window.location.search
          : searchParams.toString();
      const params = new URLSearchParams(live);

      Object.entries(updates).forEach(([key, value]) => {
        const paramKey = key as SearchParamKey;
        if (value === undefined) return;
        if (value === null) {
          params.delete(paramKey);
        } else {
          params.set(paramKey, value);
        }
      });

      const query = params.toString();
      const url = query ? `${pathname}?${query}` : pathname;
      if (replace) {
        router.replace(url);
      } else {
        router.push(url);
      }
    },
    [pathname, searchParams, router]
  );

  return useMemo(
    () => ({
      sgpAccountID: sgpAccountID || null,
      taskID: taskID || null,
      agentName: agentName || null,
      view,
      scheduleScope,
      updateParams,
    }),
    [sgpAccountID, taskID, agentName, view, scheduleScope, updateParams]
  );
}
