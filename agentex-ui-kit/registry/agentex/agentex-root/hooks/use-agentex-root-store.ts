import { PendingMessageLock } from "@/registry/agentex/agentex-root/lib/pending-message";
import type AgentexSDK from "agentex";
import type { Agent, Task } from "agentex/resources";
import { createContext, useContext } from "react";
import { createStore, StoreApi, useStore } from "zustand";

type AgentexRootStoreProps = {
  agentexClient: AgentexSDK;
  agents: Agent[];
  tasks: Task[];
};

type AgentexRootState = AgentexRootStoreProps & {
  /**
   * Map from Task ID to pending messages that should be sent after task creation.
   *
   * CRITICAL: This map instance is stable across store updates to avoid breaking
   * pending message locks that may be held by async operations. Do not recreate.
   *
   * GOTCHA: Never use this in React render logic - the map reference never changes
   * so React won't re-render when entries are added/removed.
   */
  _taskToPendingMessage: Map<Task["id"], PendingMessageLock>;
};

type AgentexRootStore = StoreApi<AgentexRootState>;

function createAgentexRootStore(
  initialState: AgentexRootStoreProps
): AgentexRootStore {
  return createStore(() => ({
    ...initialState,
    _taskToPendingMessage: new Map(),
  }));
}

const AgentexRootStoreContext = createContext<AgentexRootStore | null>(null);

function useAgentexRootStore<T>(selector: (state: AgentexRootState) => T): T {
  const store = useContext(AgentexRootStoreContext);
  if (store === null) {
    throw new Error(
      "useAgentexRootStore must be used within AgentexRootStoreContext"
    );
  }
  return useStore(store, selector);
}

function useAgentexRootStoreAPI(): AgentexRootStore {
  const store = useContext(AgentexRootStoreContext);
  if (store === null) {
    throw new Error(
      "useAgentexRootStoreAPI must be used within AgentexRootStoreContext"
    );
  }
  return store;
}

export {
  AgentexRootStoreContext,
  createAgentexRootStore,
  useAgentexRootStore,
  useAgentexRootStoreAPI,
};
export type { AgentexRootState, AgentexRootStore, AgentexRootStoreProps };
