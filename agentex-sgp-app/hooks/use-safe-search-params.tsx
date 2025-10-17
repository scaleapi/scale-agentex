import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo } from 'react';

type SafeSearchParams = {
  sgpAccountID: string | null;
  taskID: string | null;
  setTaskID: (taskID: string | null) => void;
};

/**
 * This will suspend rendering. Be sure you put suspense boundary somewhere.
 */
export function useSafeSearchParams(): SafeSearchParams {
  const SGP_ACCOUNT_ID_SEARCH_PARAM = 'account_id' as const;
  const TASK_ID_SEARCH_PARAM = 'task_id' as const;

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const sgpAccountID = searchParams.get(SGP_ACCOUNT_ID_SEARCH_PARAM);

  const taskID = searchParams.get(TASK_ID_SEARCH_PARAM);

  const setTaskID = useCallback(
    (newTaskID: string | null): void => {
      const params = new URLSearchParams(searchParams.toString());
      if (newTaskID) {
        params.set(TASK_ID_SEARCH_PARAM, newTaskID);
      } else {
        params.delete(TASK_ID_SEARCH_PARAM);
      }
      router.push(`${pathname}?${params.toString()}`);
    },
    [pathname, searchParams]
  );

  return useMemo(
    () => ({
      sgpAccountID: sgpAccountID || null,
      taskID: taskID || null,
      setTaskID,
    }),
    [sgpAccountID, taskID, setTaskID]
  );
}
