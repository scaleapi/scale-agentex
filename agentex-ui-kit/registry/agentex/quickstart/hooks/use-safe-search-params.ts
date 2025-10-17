import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

type SafeSearchParams = {
  taskID: string | null;
  setTaskID: (taskID: string | null) => void;
};

/**
 * This will suspend rendering. Be sure you put suspense boundary somewhere.
 */
export function useSafeSearchParams(): SafeSearchParams {
  const TASK_ID_SEARCH_PARAM = "task_id" as const;

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

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
    [router, pathname, searchParams]
  );

  return useMemo(
    () => ({
      taskID: taskID || null,
      setTaskID,
    }),
    [taskID, setTaskID]
  );
}
