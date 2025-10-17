import type { Agent, TaskMessageContent } from "agentex/resources";

type PendingMessage = {
  agentID: Agent["id"];
  content: TaskMessageContent;
  /**
   * Used to reduce the number of duplicate pending messages from being sent.
   * This pending message will be ignored if there are more than `checkMaxUserMessagesBeforeSend` user messages for this task.
   */
  checkMaxUserMessagesBeforeSend: number;
};

/**
 * Thread-safe lock for managing pending messages that need to be sent after task creation.
 * Ensures only one consumer can access the pending message at a time.
 */
class PendingMessageLock {
  private message: PendingMessage | null;
  private isLocked = false;
  private waiting: ((message: PendingMessage | null) => void)[] = [];

  constructor(message: PendingMessage) {
    this.message = message;
  }

  /**
   * Acquire exclusive access to the pending message.
   * If already locked, queues the request until the lock is released.
   */
  acquire(): Promise<PendingMessage | null> {
    if (this.isLocked) {
      return new Promise((resolve) => {
        this.waiting.push(resolve);
      });
    }

    this.isLocked = true;
    return Promise.resolve(this.message);
  }

  /**
   * Release the lock and optionally consume the pending message.
   * If there are waiting callers, immediately passes the lock to the next one.
   * 
   * @param shouldPopMessage If true, removes the message (consumed successfully)
   */
  release(shouldPopMessage: boolean): void {
    if (!this.isLocked) {
      throw new Error("Cannot release a lock that is not acquired.");
    }

    if (shouldPopMessage) {
      this.message = null;
    }

    const next = this.waiting.shift();
    if (next === undefined) {
      this.isLocked = false;
    } else {
      // Pass lock directly to next waiting caller
      next(this.message);
    }
  }

  /**
   * Returns true when the lock can be safely removed from the map.
   * This happens when message is consumed and no one is waiting.
   */
  get isDone(): boolean {
    return !this.isLocked && this.waiting.length === 0 && this.message === null;
  }
}

export { PendingMessageLock };
export type { PendingMessage };
