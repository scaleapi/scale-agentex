import type AgentexSDK from 'agentex';
import type { TaskMessage } from 'agentex/resources';

export const MESSAGES_PAGE_SIZE = 50;

/**
 * Fetches a single page of messages for a task.
 * API returns newest-first; this reverses to chronological order.
 */
export async function fetchMessagesPage(
  client: AgentexSDK,
  taskId: string,
  pageNumber: number,
  options?: { signal?: AbortSignal | null | undefined }
): Promise<TaskMessage[]> {
  const messages = await client.messages.list(
    { task_id: taskId, limit: MESSAGES_PAGE_SIZE, page_number: pageNumber },
    options ?? {}
  );
  return messages.slice().reverse();
}
