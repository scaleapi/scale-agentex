import { useMemo } from 'react';

import { useTaskMessages } from './use-task-messages';

import type AgentexSDK from 'agentex';
import type { TaskMessage, ToolRequestContent } from 'agentex/resources';

type WaitingForHumanResult = {
  isWaiting: boolean;
  message: string | null;
};

/**
 * Hook to detect if the agent is waiting for human input via the wait_for_human tool.
 *
 * Checks the task messages for an unanswered wait_for_human tool request and
 * extracts the context message from its parameters.
 *
 * @param agentexClient - AgentexSDK - The SDK client
 * @param taskId - string - The task ID to check
 * @returns WaitingForHumanResult - Object with isWaiting flag and message context
 */
export function useWaitingForHuman({
  agentexClient,
  taskId,
}: {
  agentexClient: AgentexSDK;
  taskId: string;
}): WaitingForHumanResult {
  const { data: queryData } = useTaskMessages({ agentexClient, taskId });

  return useMemo<WaitingForHumanResult>(() => {
    const messages = queryData?.messages ?? [];

    // Find all tool requests and responses
    const toolRequests = messages.filter(
      (m): m is TaskMessage & { content: ToolRequestContent } =>
        m.content.type === 'tool_request'
    );

    const toolResponses = new Set(
      messages
        .filter(m => m.content.type === 'tool_response')
        .map(m => (m.content as { tool_call_id?: string }).tool_call_id)
    );

    // Find the last unanswered wait_for_human tool request
    const waitingToolRequest = [...toolRequests]
      .reverse()
      .find(
        req =>
          req.content.name === 'wait_for_human' &&
          !toolResponses.has(req.content.tool_call_id)
      );

    if (!waitingToolRequest) {
      return { isWaiting: false, message: null };
    }

    // Extract message from parameters
    const params = waitingToolRequest.content.arguments as {
      message?: string;
    };
    const message = params?.message || null;

    return { isWaiting: true, message };
  }, [queryData]);
}
