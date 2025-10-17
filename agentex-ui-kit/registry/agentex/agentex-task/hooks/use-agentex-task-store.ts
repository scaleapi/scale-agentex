import { useAgentexRootStore } from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import type { IDeltaAccumulator } from "agentex/lib";
import type { Agent, Task, TaskMessage } from "agentex/resources";
import { createContext, useContext, useMemo } from "react";
import { createStore, StoreApi, useStore } from "zustand";

type AgentexTaskStoreProps = {
  signal: AbortSignal;
  taskID: Task["id"];
  /**
   * Agents that this can use.
   */
  taskAgentIDs: Agent["id"][];
  messages: TaskMessage[];
  /**
   * This is only used for sync ACP agents.
   */
  deltaAccumulator: IDeltaAccumulator | null;
};

type AgentexTaskState = AgentexTaskStoreProps & {
  streamStatus: "loading" | "ready" | "reconnecting" | "error";
  isPendingMessagesSent: boolean;
};

type AgentexTaskStore = StoreApi<AgentexTaskState>;

function createAgentexTaskStore(
  initialState: AgentexTaskStoreProps
): AgentexTaskStore {
  return createStore(() => ({
    ...initialState,
    streamStatus: "loading",
    isPendingMessagesSent: false,
  }));
}

const AgentexTaskStoreContext = createContext<AgentexTaskStore | null>(null);

function useAgentexTaskStore<T>(selector: (state: AgentexTaskState) => T): T {
  const store = useContext(AgentexTaskStoreContext);
  if (store === null) {
    throw new Error("useAgentexTaskStore must be used within AgentexTask");
  }
  return useStore(store, selector);
}

function useAgentexTask(): Task | undefined {
  const taskID = useAgentexTaskStore((s) => s.taskID);
  const tasks = useAgentexRootStore((s) => s.tasks);
  return tasks.find((t) => t.id === taskID);
}

function useAgentexTaskAgents(): Agent[] {
  const agents = useAgentexRootStore((s) => s.agents);
  const taskAgentIDs = useAgentexTaskStore((s) => s.taskAgentIDs);
  return useMemo(
    () => agents.filter((agent) => taskAgentIDs.includes(agent.id)),
    [agents, taskAgentIDs]
  );
}

export {
  AgentexTaskStoreContext,
  createAgentexTaskStore,
  useAgentexTask,
  useAgentexTaskAgents,
  useAgentexTaskStore,
};
export type { AgentexTaskState, AgentexTaskStore, AgentexTaskStoreProps };
