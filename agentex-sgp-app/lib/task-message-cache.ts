import type {
  AgentexRootState,
  AgentexRootStore,
} from '@/hooks/use-agentex-root-store';
import type { Task, TaskMessage } from 'agentex/resources';
import { produce } from 'immer';

/**
 * Populates the root-level taskMessageCache with the first message of each
 * task returned during initial bootstrap. This enables cross-task UI (e.g.
 * task title/subtitle) to render without loading full message histories.
 *
 * Notes:
 * - Only runs on bootstrap for tasks we fetched up-front.
 * - Ongoing updates for a specific task are handled by `AgentexTask` which
 *   subscribes to its task store and mirrors changes into the root cache.
 */
export async function cacheFirstMessageForTasks(
  store: AgentexRootStore,
  signal: AbortSignal
): Promise<void> {
  const { tasks, agentexClient } = store.getState();
  await Promise.all(
    tasks.map(async (task): Promise<void> => {
      const [firstMessage] = await agentexClient.messages.list(
        {
          task_id: task.id,
          limit: 1,
        },
        { signal }
      );

      if (signal.aborted) {
        return;
      }

      if (firstMessage !== undefined) {
        store.setState((prev) => ({
          ...prev,
          taskMessageCache: produce(prev.taskMessageCache, (draft) => {
            const cacheIndex = draft.findIndex(
              (entry) => entry.taskID === task.id
            );
            if (cacheIndex === -1) {
              draft.push({ taskID: task.id, messages: [firstMessage] });
            }
            return draft;
          }),
        }));
      }
    })
  );
}

/**
 * Mirrors task-scoped message updates into the root store's taskMessageCache.
 *
 * Why: Cross-task UI needs a lightweight way to show preview data (e.g.,
 * first message) without loading the full history every render. We seed this
 * cache on bootstrap and keep it synced for tasks that are opened.
 */
export function updateRootTaskMessageCache(
  rootStore: AgentexRootStore,
  taskID: Task['id'],
  messages: TaskMessage[]
): void {
  rootStore.setState(
    (prev): AgentexRootState => ({
      ...prev,
      taskMessageCache: produce(prev.taskMessageCache, (draft) => {
        const cachedIndex = draft.findIndex((cache) => cache.taskID === taskID);
        if (cachedIndex !== -1) {
          draft[cachedIndex]!.messages = messages;
        } else {
          draft.push({ taskID, messages });
        }
        return draft;
      }),
    })
  );
}
