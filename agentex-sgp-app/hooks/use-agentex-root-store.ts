import { PendingMessageLock } from '@/lib/pending-message';
import type AgentexSDK from 'agentex';
import type { Agent, Task, TaskMessage } from 'agentex/resources';
import { createContext, useContext } from 'react';
import { createStore, StoreApi, useStore } from 'zustand';

type AgentexRootStoreProps = {
  agentexClient: AgentexSDK;
  agents: Agent[];
  tasks: Task[];
};

type AgentexRootState = AgentexRootStoreProps & {
  /**
   * Cross-task message preview cache (first message, etc.) used for list UI.
   *
   * This duplicates per-task state intentionally: we seed it during root
   * bootstrap, then keep it in sync for any task that mounts via
   * `AgentexTask` by subscribing to that task's message updates.
   */
  taskMessageCache: { taskID: Task['id']; messages: TaskMessage[] }[];

  /**
   * Map from Task ID to a lock guarding a single pending first message.
   *
   * Invariants:
   * - This map object should not be recreated; it is created once with the
   *   store and mutated in place.
   * - React state updates are not triggered by its identity changes.
   * - Values are cleaned up by consumers when `lock.isDone` becomes true.
   */
  _taskToPendingMessage: Map<Task['id'], PendingMessageLock>;
};

type AgentexRootStore = StoreApi<AgentexRootState>;

function createAgentexRootStore(
  initialState: AgentexRootStoreProps
): AgentexRootStore {
  return createStore(() => ({
    ...initialState,
    taskMessageCache: [],
    _taskToPendingMessage: new Map(),
  }));
}

const AgentexRootStoreContext = createContext<AgentexRootStore | null>(null);

function useAgentexRootStore<T>(selector: (state: AgentexRootState) => T): T {
  const store = useContext(AgentexRootStoreContext);
  if (store === null) {
    throw new Error(
      'useAgentexRootStore must be used within AgentexRootStoreContext'
    );
  }
  return useStore(store, selector);
}

function useAgentexRootStoreAPI(): AgentexRootStore {
  const store = useContext(AgentexRootStoreContext);
  if (store === null) {
    throw new Error(
      'useAgentexRootStoreAPI must be used within AgentexRootStoreContext'
    );
  }
  return store;
}

export {
  AgentexRootStoreContext,
  createAgentexRootStore,
  useAgentexRootStore,
  useAgentexRootStoreAPI
};
export type { AgentexRootState, AgentexRootStore, AgentexRootStoreProps };

