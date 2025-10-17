import { useAgentexRootStore } from '@/hooks/use-agentex-root-store';
import type { IDeltaAccumulator } from 'agentex/lib';
import type { Agent, Task, TaskMessage } from 'agentex/resources';
import { createContext, useContext, useMemo } from 'react';
import { createStore, ExtractState, useStore } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

type AgentexTaskStoreProps = {
  signal: AbortSignal;
  taskID: Task['id'];
  /**
   * Agents that this can use.
   */
  taskAgentIDs: Agent['id'][];
  messages: TaskMessage[];
  /**
   * This is only used for sync ACP agents.
   */
  deltaAccumulator: IDeltaAccumulator | null;
};

type AgentexTaskState = AgentexTaskStoreProps & {
  streamStatus: 'loading' | 'ready' | 'reconnecting' | 'error';
  isPendingMessagesSent: boolean;
};

function createAgentexTaskStore(initialState: AgentexTaskStoreProps) {
  return createStore(
    subscribeWithSelector(() => ({
      ...initialState,
      streamStatus: 'loading',
      isPendingMessagesSent: false,
    }))
  );
}

type AgentexTaskStore = ReturnType<typeof createAgentexTaskStore>;

const AgentexTaskStoreContext = createContext<AgentexTaskStore | null>(null);

function useAgentexTaskStore<T>(selector: (state: ExtractState<AgentexTaskStore>) => T): T {
  const store = useContext(AgentexTaskStoreContext);
  if (store === null) {
    throw new Error('useAgentexTaskStore must be used within AgentexTask');
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
  useAgentexTaskStore
};
export type { AgentexTaskState, AgentexTaskStore, AgentexTaskStoreProps };

