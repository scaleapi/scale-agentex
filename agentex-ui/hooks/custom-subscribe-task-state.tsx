import { IDeltaAccumulator } from 'agentex/lib';
import { aggregateMessageEvents } from 'agentex/lib/aggregate-message-events';
import { compareDateStrings } from 'agentex/lib/compare-date-strings';
import { taskStreamEventGenerator } from 'agentex/lib/task-stream-event-generator';

import type { Agentex } from 'agentex';
import type { Agent, Task, TaskMessage } from 'agentex/resources';

/**
 *
 * TODO(msun): DELETE THIS FILE AFTER IMPLEMENTING ORDER BY IN MESSAGE LIST ENDPOINT
 *
 * This file is a near identical copy of the resources/messages/messages.ts file in the agentex SDK,
 * with the exception of line 144, where we add a high default limit to the message list endpoint
 * to avoid the default 50 message limit that is set in the agentex SDK.
 * The better long term solution is to implement the order by in the message list endpoint and add
 * infinite scrolling to the task messages component.
 */

type TaskIdentifier = { taskID: string };

/**
 * This is useful to subscribe your client application state with the Agentex API.
 *
 * Treat all arguments from callbacks as readonly! If you'd like to modify the state in your application, create a copy.
 */
export interface ITaskEventListener {
  onTaskChange(task: Readonly<Task>): void;
  onAgentsChange(agents: ReadonlyArray<Readonly<Agent>>): void;
  onMessagesChange(messages: ReadonlyArray<Readonly<TaskMessage>>): void;
  onError(errorMessage: string): void;
  onStreamStatusChange(
    status: 'connected' | 'reconnecting' | 'disconnected'
  ): void;
}

/**
 * This reconnect policy resets whenever a successful connection is made to the task stream.
 *
 * e.g. Successful connection -> error (count 1) -> error (count 2) -> successful connection (reset) -> error (count 1)
 */
type TaskStreamReconnectPolicy = {
  /** immediately reconnect until we see this many errors */
  startBackoffOnErrorNum?: number;
  /** reconnect up to this many times, then throw the error. < 0 indicates no limit */
  maxContinuousErrors?: number;
  /** the first backoff is this many milliseconds */
  exponentialBackoffMultiplierMs?: number;
  /** then backoff time grows by this factor exponentially */
  exponentialBackoffBase?: number;
};

type AbortedReturn = {
  aborted: true;
  taskStreamReconnectLimitReached?: undefined;
  error?: undefined;
};

type ErrorReturn = {
  taskStreamReconnectLimitReached: boolean;
  error: unknown;
  aborted?: undefined;
};

/**
 * Subscribes to real-time task state changes, including task updates, agent changes, and message events.
 * Automatically handles reconnection with exponential backoff on connection failures.
 *
 * TODO: add cursor + limit to messages so you don't have to load all messages.
 *
 * @param client - The Agentex client instance for API communication
 * @param taskIdentifier - Right now this is just the taskID, but we should allow taskName later.
 * @param eventListener - Get the latest task state through these callbacks.
 * @param options.signal - AbortSignal to cancel the subscription. This is necessary to prevent resource leaks!
 * @param options.taskStreamReconnectPolicy - Override the default reconnect policy. Defaults to `{
 *   startBackoffOnErrorNum: 2,
 *   maxContinuousErrors: 8,
 *   exponentialBackoffMultiplierMs: 500,
 *   exponentialBackoffBase: 2
 * }`
 * @returns Promise that resolves with `{ aborted: true }` if the abort signal was triggered,
 * otherwise `{ taskStreamReconnectLimitReached: boolean; error: unknown }`
 * where `taskStreamReconnectLimitReached` indicates if `taskStreamReconnectPolicy.maxContinuousErrors` reached and error was the last caught error.
 * This promise will never reject.
 */
export async function subscribeTaskState(
  client: Agentex,
  taskIdentifier: TaskIdentifier,
  eventListener: ITaskEventListener,
  options?: {
    signal?: AbortSignal | undefined | null;
    taskStreamReconnectPolicy?: TaskStreamReconnectPolicy;
  }
): Promise<AbortedReturn | ErrorReturn> {
  const { taskID } = taskIdentifier;
  const { signal, taskStreamReconnectPolicy } = options ?? {};

  const startBackoffOnErrorNum =
    taskStreamReconnectPolicy?.startBackoffOnErrorNum ?? 2;
  const continuousErrorRetryLimit =
    taskStreamReconnectPolicy?.maxContinuousErrors ?? 8;
  const exponentialBackoffMultiplierMS =
    taskStreamReconnectPolicy?.exponentialBackoffMultiplierMs ?? 500;
  const exponentialBackoffBase =
    taskStreamReconnectPolicy?.exponentialBackoffBase ?? 2;

  // current subscription state
  let _task: Task | null = null;
  let _agents: Agent[] | null = null;
  let messages: TaskMessage[] | null = null;
  let deltaAccumulator: IDeltaAccumulator | null = null;
  let continuousAPIErrorCount = 0;

  // RETRY WHILE LOOP
  while (!signal?.aborted) {
    // RETRY WHILE LOOP -> STREAM TRY / CATCH
    try {
      for await (const taskEvent of taskStreamEventGenerator(
        client,
        { taskID },
        { signal }
      )) {
        if (signal?.aborted) {
          return { aborted: true };
        }

        // RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY / CATCH
        try {
          switch (taskEvent.type) {
            case 'connected':
              // RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: connected
              continuousAPIErrorCount = 0;

              // pause reading from stream until we initialize state
              [_task, _agents, messages] = await Promise.all([
                client.tasks.retrieve(taskID, null, { signal }).then(res => {
                  eventListener.onTaskChange(res);
                  return res;
                }),
                client.agents
                  .list({ task_id: taskID }, { signal })
                  .then(res => {
                    eventListener.onAgentsChange(res);
                    return res;
                  }),
                client.messages
                  .list({ task_id: taskID, limit: 1000 }, { signal })
                  .then(res => {
                    eventListener.onMessagesChange(res);
                    return res;
                  }),
              ]);

              // reset delta accumulator on connected event
              deltaAccumulator = null;

              eventListener.onStreamStatusChange('connected');
              // END RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: connected
              break;
            case 'error':
              // RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: error
              eventListener.onError(taskEvent.message);
              // END RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: error
              break;
            case 'delta':
            case 'done':
            case 'full':
            case 'start':
              // RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: task message update
              if (messages === null) {
                throw new Error(
                  `"${taskEvent.type}" event received before "connected" event. This error will result in a retry if we have retries left.`
                );
              }

              const aggregationResult = aggregateMessageEvents(
                messages,
                deltaAccumulator,
                [taskEvent]
              );
              ({ messages, deltaAccumulator } = aggregationResult);

              eventListener.onMessagesChange(messages);

              // pause listening to stream until all problematic messages are re-fetched
              await Promise.all(
                Array.from(aggregationResult.refetchMessageIDs.values()).map(
                  async refetchMessageID => {
                    if (!refetchMessageID) {
                      return;
                    }
                    const updatedMessage = await client.messages.retrieve(
                      refetchMessageID,
                      { signal }
                    );

                    // update message sync
                    messages =
                      messages?.map(message =>
                        message.id === refetchMessageID &&
                        compareDateStrings(
                          message.updated_at,
                          updatedMessage.updated_at
                        ) <= 0
                          ? updatedMessage
                          : message
                      ) ?? null;

                    if (messages !== null) {
                      eventListener.onMessagesChange(messages);
                    }
                  }
                )
              );
              // END RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: task message update
              break;
            default:
              // RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: unknown
              taskEvent.type satisfies undefined;
              console.warn('Unknown task event', taskEvent);
              // END RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY -> EVENT: unknown
              break;
          }
          // END RETRY WHILE LOOP -> STREAM TRY -> EXECUTION TRY
        } catch (executionError) {
          // RETRY WHILE LOOP -> STREAM TRY -> EXECUTION CATCH
          if (signal?.aborted) {
            return { aborted: true };
          }

          eventListener.onStreamStatusChange('disconnected');
          return {
            taskStreamReconnectLimitReached: false,
            error: executionError,
          };
          // END RETRY WHILE LOOP -> STREAM TRY -> EXECUTION CATCH
        }
      }
    } catch (streamError) {
      if (signal?.aborted) {
        return { aborted: true };
      }

      // this gets incremented until a successful "connected" event
      continuousAPIErrorCount++;

      if (
        continuousErrorRetryLimit >= 0 &&
        continuousAPIErrorCount > continuousErrorRetryLimit
      ) {
        eventListener.onStreamStatusChange('disconnected');
        return { taskStreamReconnectLimitReached: true, error: streamError };
      }

      console.warn(
        'subscribeTaskState encountered an error and will attempt to reconnect',
        streamError
      );

      eventListener.onStreamStatusChange('reconnecting');
      if (continuousAPIErrorCount >= startBackoffOnErrorNum) {
        await new Promise(resolve =>
          setTimeout(
            resolve,
            exponentialBackoffMultiplierMS *
              Math.pow(
                exponentialBackoffBase,
                continuousAPIErrorCount - startBackoffOnErrorNum
              )
          )
        );
      }
    }
  }

  return { aborted: true };
}
