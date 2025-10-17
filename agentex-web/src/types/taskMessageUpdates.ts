import type {TaskStreamErrorEvent} from 'agentex/lib/schemas/task-stream';
import type {TaskMessageUpdate} from 'agentex/resources';

/**
 * Callback type for handling stream events/chunks
 */
export type StreamUpdateCallback = (data: TaskMessageUpdate) => void;

/**
 * Callback type for handling stream errors
 */
export type ErrorCallback = (error: TaskStreamErrorEvent | unknown) => void;

/**
 * Callback type for handling stream connection events
 */
export type ConnectionCallback = () => void;

/**
 * Callback type for handling stream completion
 */
export type CompletionCallback = (taskId: string) => void;
