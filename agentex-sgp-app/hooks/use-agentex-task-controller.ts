import {
  AgentexRootStore,
  useAgentexRootStoreAPI,
} from "@/hooks/use-agentex-root-store";
import {
  AgentexTaskStore,
  AgentexTaskStoreContext,
  useAgentexTask,
} from "@/hooks/use-agentex-task-store";
import {
  agentRPCNonStreaming,
  agentRPCWithStreaming,
  aggregateMessageEvents,
} from "agentex/lib";
import type { Agent, TaskMessage, TaskMessageContent } from "agentex/resources";
import { useCallback, useContext, useMemo } from "react";
import { v4 } from "uuid";
import { useStore } from "zustand";

async function handleSendMessage(
  rootStore: AgentexRootStore,
  taskStore: AgentexTaskStore,
  agentID: Agent["id"],
  content: TaskMessageContent
): Promise<void> {
  const initialState = taskStore.getState();
  const initialRootState = rootStore.getState();
  const agent = initialRootState.agents.find((agent) => agent.id === agentID);

  if (agent === undefined) {
    throw new Error(`Agent with ID ${agentID} not found in AgentexRootStore`);
  }

  // Route message handling based on agent communication pattern
  switch (agent.acp_type) {
    case "agentic": {
      // Fire-and-forget pattern: send event, agent handles async response
      const response = await agentRPCNonStreaming(
        initialRootState.agentexClient,
        { agentID },
        "event/send",
        { task_id: initialState.taskID, content },
        { signal: initialState.signal }
      );

      if (response.error != null) {
        throw new Error(response.error.message);
      }

      break;
    }
    case "sync": {
      // Streaming pattern: immediate response with real-time updates
      // First display user message optimistically for better UX
      const tempUserMessage: TaskMessage = {
        id: v4(),
        content,
        task_id: initialState.taskID,
        created_at: new Date().toISOString(),
        streaming_status: "DONE",
        updated_at: new Date().toISOString(),
      };
      taskStore.setState({
        messages: [...initialState.messages, tempUserMessage],
      });

      // Stream agent response and update UI in real-time
      for await (const response of agentRPCWithStreaming(
        initialRootState.agentexClient,
        { agentID },
        "message/send",
        { task_id: initialState.taskID, content },
        { signal: initialState.signal }
      )) {
        if (response.error != null) {
          throw new Error(response.error.message);
        }

        const { messages, deltaAccumulator } = taskStore.getState();
        const result = aggregateMessageEvents(messages, deltaAccumulator, [
          response.result,
        ]);

        taskStore.setState({
          messages: result.messages,
          deltaAccumulator: result.deltaAccumulator,
        });
      }

      // Replace temporary user message with server-authoritative version
      const beforeSyncState = taskStore.getState();
      const finalMessages = await rootStore
        .getState()
        .agentexClient.messages.list(
          { task_id: beforeSyncState.taskID },
          { signal: beforeSyncState.signal }
        );
      taskStore.setState({
        messages: finalMessages,
      });
      break;
    }
    default: {
      throw new Error(
        `Unsupported agent acp_type: ${agent.acp_type satisfies never}`
      );
    }
  }
}

/**
 * TODO: add more controls
 */
type AgentexTaskController = {
  isSendMessageEnabled: boolean;
  sendMessage: (
    agentID: Agent["id"],
    content: TaskMessageContent
  ) => Promise<void>;
};

function useAgentexTaskController(): AgentexTaskController {
  const store = useContext(AgentexTaskStoreContext);
  if (store === null) {
    throw new Error("useAgentexTaskController must be used within AgentexTask");
  }
  const rootStore = useAgentexRootStoreAPI();

  const task = useAgentexTask();
  const isPendingMessagesSent = useStore(store, (s) => s.isPendingMessagesSent);

  // Only allow messaging when task exists, is running, and initial pending messages are handled
  const isSendMessageEnabled =
    task !== undefined && task.status === "RUNNING" && isPendingMessagesSent;

  const sendMessage = useCallback<AgentexTaskController["sendMessage"]>(
    (agentID, content) => handleSendMessage(rootStore, store, agentID, content),
    [store, rootStore]
  );

  return useMemo(
    () => ({
      isSendMessageEnabled,
      sendMessage,
    }),
    [isSendMessageEnabled, sendMessage]
  );
}

export { handleSendMessage, useAgentexTaskController };
export type { AgentexTaskController };

