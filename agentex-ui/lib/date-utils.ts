import type { TaskMessage } from 'agentex/resources';

export function calculateThinkingTime(
  message: TaskMessage,
  nextBlockTimestamp: TaskMessage['created_at']
): number | null {
  if (!message.created_at || !nextBlockTimestamp) {
    return null;
  }

  const promptDate = new Date(message.created_at);
  const responseDate = new Date(nextBlockTimestamp);
  const diffMs = responseDate.getTime() - promptDate.getTime();
  const diffSec = diffMs / 1000;

  return diffSec < 10 ? Math.round(diffSec * 10) / 10 : Math.round(diffSec);
}
