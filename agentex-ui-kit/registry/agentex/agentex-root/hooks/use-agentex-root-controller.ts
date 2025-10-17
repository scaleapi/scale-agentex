import { useAgentexRootStoreAPI } from "@/registry/agentex/agentex-root/hooks/use-agentex-root-store";
import {
  PendingMessage,
  PendingMessageLock,
} from "@/registry/agentex/agentex-root/lib/pending-message";
import { agentRPCNonStreaming } from "agentex/lib";
import type { Agent, Task, TaskMessageContent } from "agentex/resources";
import { useMemo } from "react";

type AgentexRootController = {
  /**
   * IMPORTANT: This function does not actually send `messageContent` to the task. It only creates a `PendingMessage`.
   * The message is sent automatically when `AgentexTask` is first rendered with this taskID.
   * This is because `AgentexTask` needs to be able to stream the response into its state.
   * If you don't want to display any UI for some reason, you can also just render an empty `<AgentexTask />` somewhere.
   */
  createTask: (
    agentID: Agent["id"],
    name: string | null,
    messageContent: TaskMessageContent | null,
    taskParams?: Record<string, unknown> | null
  ) => Promise<Task>;
  /**
   * @param callback This is called with the pending message (if any) once other callers release the lock.
   * The pending message is removed if the promise returned by the callback resolves.
   * If the promise is rejected, the pending message is not removed.
   */
  popPendingMessageForTask: (
    taskID: Task["id"],
    callback: (pendingMessage: PendingMessage | null) => Promise<void>
  ) => void;
};

function useAgentexRootController(): AgentexRootController {
  const store = useAgentexRootStoreAPI();

  return useMemo(
    () => ({
      createTask: async (agentID, name, messageContent, params) => {
        const response = await agentRPCNonStreaming(
          store.getState().agentexClient,
          { agentID },
          "task/create",
          {
            name,
            ...(params !== undefined ? { params } : null),
          }
        );

        if (response.error != null) {
          throw new Error(response.error.message);
        }

        // Add task to store if it doesn't already exist (avoid duplicates)
        const beforeUpdateState = store.getState();
        if (beforeUpdateState.tasks.every((t) => t.id !== response.result.id)) {
          store.setState({
            tasks: [...beforeUpdateState.tasks, response.result],
          });
        }

        // Queue message to be sent once task context is initialized
        if (messageContent !== null) {
          store.getState()._taskToPendingMessage.set(
            response.result.id,
            new PendingMessageLock({
              agentID,
              content: messageContent,
              checkMaxUserMessagesBeforeSend: 0,
            })
          );
        }

        return response.result;
      },
      popPendingMessageForTask: (taskID, callback) => {
        const lock = store.getState()._taskToPendingMessage.get(taskID);
        if (lock === undefined) {
          callback(null);
        } else {
          lock
            .acquire()
            .then(callback)
            .then(
              // if callback resolves, release the lock and pop the pending message
              () => {
                lock.release(true);
              },
              // if callback rejects, release the lock but do not pop the pending message
              () => {
                lock.release(false);
              }
            )
            // cleanup map if the pending message lock is done
            .finally(() => {
              if (lock.isDone) {
                store.getState()._taskToPendingMessage.delete(taskID);
              }
            });
        }
      },
    }),
    [store]
  );
}

export { useAgentexRootController };
export type { AgentexRootController };

