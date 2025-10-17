import { useAgentexRootController } from '@/hooks/use-agentex-root-controller';
import {
  AgentexRootStore,
  useAgentexRootStoreAPI,
} from '@/hooks/use-agentex-root-store';
import { handleSendMessage } from '@/hooks/use-agentex-task-controller';
import {
  AgentexTaskStore,
  AgentexTaskStoreContext,
  createAgentexTaskStore,
} from '@/hooks/use-agentex-task-store';
import type { PendingMessage } from '@/lib/pending-message';
import { updateRootTaskMessageCache } from '@/lib/task-message-cache';
import { subscribeTaskState } from 'agentex/lib';
import type { Task } from 'agentex/resources';
import { useEffect, useRef, useState } from 'react';

function bootstrapTask(
  rootStore: AgentexRootStore,
  taskID: Task['id'],
  signal: AbortSignal,
  onError: (errorMessage: string) => void,
  acquirePendingMessage: (
    callback: (pendingMessage: PendingMessage | null) => Promise<void>
  ) => void
): Promise<AgentexTaskStore> {
  const initialRootState = rootStore.getState();

  return new Promise((resolve) => {
    let agentsInitialized = false;
    let messagesInitialized = false;

    const initializerCallback = (event: 'agents' | 'messages') => {
      if (event === 'agents') {
        agentsInitialized = true;
      } else if (event === 'messages') {
        messagesInitialized = true;
      }

      if (!agentsInitialized || !messagesInitialized) {
        return;
      }

      // TODO: move this to the createTask function and make sure we get all the deltas we need
      // Send any queued pending messages for this task
      // This is done during bootstrapping rather than during createTask to make sure no deltas are missed.
      acquirePendingMessage(async (pendingMessage) => {
        if (pendingMessage !== null) {
          // Check if we should still send this message (avoid spam from rapid task creation)
          const messagesBeforeSend = await rootStore
            .getState()
            .agentexClient.messages.list({ task_id: taskID }, { signal });

          if (
            messagesBeforeSend.filter((m) => m.content.author === 'user')
              .length <= pendingMessage.checkMaxUserMessagesBeforeSend
          ) {
            await handleSendMessage(
              rootStore,
              store,
              pendingMessage.agentID,
              pendingMessage.content
            );
          }
        }

        // Mark pending messages as processed to enable user messaging
        store.setState({ isPendingMessagesSent: true });
      });
      resolve(store);
    };

    const store = createAgentexTaskStore({
      signal,
      taskID,
      taskAgentIDs: [],
      messages: [],
      deltaAccumulator: null,
    });

    subscribeTaskState(
      initialRootState.agentexClient,
      { taskID },
      {
        onAgentsChange(updatedTaskAgents) {
          store.setState({ taskAgentIDs: updatedTaskAgents.map((a) => a.id) });

          rootStore.setState((prev) => ({
            agents: prev.agents.map((a) => {
              const updatedTaskAgent = updatedTaskAgents.find(
                (agent) => agent.id === a.id
              );
              if (updatedTaskAgent !== undefined) {
                return updatedTaskAgent;
              }
              return a;
            }),
          }));

          initializerCallback('agents');
        },
        onError(errorMessage) {
          onError(errorMessage);
        },
        onMessagesChange(messages) {
          store.setState({ messages: [...messages] });
          initializerCallback('messages');
        },
        onStreamStatusChange(streamStatus) {
          switch (streamStatus) {
            case 'connected':
              store.setState({ streamStatus: 'ready' });
              break;
            case 'reconnecting':
              store.setState({ streamStatus: 'reconnecting' });
              break;
            case 'disconnected':
              store.setState({ streamStatus: 'error' });
              break;
            default:
              streamStatus satisfies never;
              onError(`Unknown stream status: ${streamStatus}`);
              break;
          }
        },
        onTaskChange(updatedTask) {
          rootStore.setState((prev) => ({
            tasks: prev.tasks.map((t) =>
              t.id === updatedTask.id ? updatedTask : t
            ),
          }));
        },
      },
      { signal }
    );
  });
}

type AgentexTaskProps = {
  taskID: Task['id'];
  fallback?: React.ReactNode;
  children?: React.ReactNode;
  onError?: (error: unknown) => void;
};

function AgentexTask({
  children,
  fallback,
  taskID,
  onError,
}: AgentexTaskProps) {
  const [store, setStore] = useState<AgentexTaskStore | null>(null);
  const rootStore = useAgentexRootStoreAPI();
  const { popPendingMessageForTask } = useAgentexRootController();

  const onErrorRef = useRef<typeof onError>(onError);
  // keep onErrorRef in sync
  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  // bootstrap
  useEffect(() => {
    let current = true;
    let unsubscribeRoot: (() => void) | undefined = undefined;
    const abortController = new AbortController();

    setStore(null);

    bootstrapTask(
      rootStore,
      taskID,
      abortController.signal,
      (errorMessage) => onErrorRef.current?.({ message: errorMessage }),
      (...args) => popPendingMessageForTask(taskID, ...args)
    ).then(
      (store) => {
        // IMPORTANT: must exit if not current. this means that we are already all cleaned up.
        if (!current) {
          return;
        }

        // Keep root cache in sync with this task's live messages while mounted.
        updateRootTaskMessageCache(
          rootStore,
          taskID,
          store.getState().messages
        );
        unsubscribeRoot = store.subscribe(
          (s) => s.messages,
          (messages) => updateRootTaskMessageCache(rootStore, taskID, messages)
        );

        // update root store
        setStore(store);
      },
      (error) => {
        // IMPORTANT: must exit if not current. this means that we are already all cleaned up.
        if (!current) {
          return;
        }
        if (onErrorRef.current !== undefined) {
          onErrorRef.current(error);
          return;
        }
        throw error;
      }
    );

    return () => {
      current = false;
      unsubscribeRoot?.();
      abortController.abort();
    };
  }, [setStore, rootStore, taskID, popPendingMessageForTask]);

  // loading
  if (store === null) {
    return <>{fallback}</>;
  }

  // render
  return (
    <AgentexTaskStoreContext.Provider value={store}>
      {children}
    </AgentexTaskStoreContext.Provider>
  );
}

export { AgentexTask };
