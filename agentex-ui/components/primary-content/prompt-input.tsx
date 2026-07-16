'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { closeBrackets } from '@codemirror/autocomplete';
import { json } from '@codemirror/lang-json';
import { Prec } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import CodeMirror from '@uiw/react-codemirror';
import { DataContent, TextContent } from 'agentex/resources';
import { ArrowUp, Square, X } from 'lucide-react';

import { useAgentexClient } from '@/components/providers';
import { IconButton } from '@/components/ui/icon-button';
import { Switch } from '@/components/ui/switch';
import { toast } from '@/components/ui/toast';
import { useCreateTask } from '@/hooks/use-create-task';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import {
  useInterruptTurn,
  useSendMessage,
  useTaskMessages,
} from '@/hooks/use-task-messages';
import { useTask } from '@/hooks/use-tasks';
import { isTaskTerminalStatus } from '@/lib/types';

type PromptInputProps = {
  prompt: string;
  setPrompt: (prompt: string) => void;
};

const DEFAULT_JSON_PROMPT = '{\n  \n}';
// CodeMirror theme to remove focus outline
const noOutlineTheme = EditorView.theme({
  '&.cm-editor.cm-focused': {
    outline: 'none',
  },
  '.cm-content': {
    backgroundColor: 'inherit',
  },
  '.cm-editor': {
    backgroundColor: 'inherit',
  },
  '.cm-cursor': {
    borderLeftColor: 'var(--color-foreground)',
  },
});

export function PromptInput({ prompt, setPrompt }: PromptInputProps) {
  const { taskID, agentName, updateParams } = useSafeSearchParams();
  const [isClient, setIsClient] = useState(false);
  const [isSendingJSON, setIsSendingJSON] = useState(false);
  const [isTaskParamsOpen, setIsTaskParamsOpen] = useState(false);
  const [taskParams, setTaskParams] = useState('');
  const [queuedMessage, setQueuedMessage] = useState<{
    text: string;
    isJson: boolean;
  } | null>(null);
  const taskParamsViewRef = useRef<EditorView | null>(null);

  const { agentexClient } = useAgentexClient();

  const createTaskMutation = useCreateTask({ agentexClient });
  const sendMessageMutation = useSendMessage({ agentexClient });
  const interruptTurnMutation = useInterruptTurn({ agentexClient });
  const { data: task } = useTask({ agentexClient, taskId: taskID ?? '' });
  const { rpcStatus } = useTaskMessages({
    agentexClient,
    taskId: taskID ?? '',
  });

  const isStreaming = rpcStatus === 'pending';

  const textInputRef = useRef<HTMLTextAreaElement>(null);
  const codeMirrorViewRef = useRef<EditorView | null>(null);
  const wasStreamingRef = useRef(false);

  const isTaskTerminal = useMemo(() => {
    if (!taskID || !task) return false;
    return isTaskTerminalStatus(task.status);
  }, [taskID, task]);

  const handleSetJson = useCallback(
    (value: boolean) => {
      if (value && !prompt.trim()) {
        setPrompt(DEFAULT_JSON_PROMPT);
      } else if (!value && !prompt.trim()) {
        setPrompt('');
      }
      setIsSendingJSON(value);
    },
    [prompt, setPrompt]
  );

  useEffect(() => {
    setIsClient(true);
  }, []);

  // Focus the prompt input when taskID is cleared
  useEffect(() => {
    if (!taskID && isClient) {
      requestAnimationFrame(() => {
        if (isSendingJSON) {
          codeMirrorViewRef.current?.focus();
        } else {
          textInputRef.current?.focus();
        }
      });
    }
  }, [taskID, isClient, isSendingJSON]);

  const isDisabled = useMemo(
    () => !agentName || !isClient || isTaskTerminal,
    [agentName, isClient, isTaskTerminal]
  );

  const performSend = useCallback(
    async (rawPrompt: string, asJson: boolean) => {
      if (!agentName || !rawPrompt.trim()) return;

      if (asJson) {
        try {
          JSON.parse(rawPrompt);
        } catch {
          toast.error('Invalid JSON');
          return;
        }
      }

      let currentTaskId = taskID;

      if (!currentTaskId) {
        let extraTaskParams: Record<string, unknown> = {};
        if (taskParams.trim()) {
          try {
            extraTaskParams = JSON.parse(taskParams);
          } catch {
            toast.error('Invalid Task Parameters JSON');
            return;
          }
        }

        const task = await createTaskMutation.mutateAsync({
          agentName: agentName,
          params: {
            ...extraTaskParams,
            description: rawPrompt,
            content: rawPrompt,
          },
        });
        currentTaskId = task.id;
        updateParams({ [SearchParamKey.TASK_ID]: currentTaskId });
      }

      const content: TextContent | DataContent = asJson
        ? {
            type: 'data',
            author: 'user',
            data: JSON.parse(rawPrompt) as Record<string, unknown>,
          }
        : {
            type: 'text',
            author: 'user',
            format: 'plain',
            attachments: [],
            content: rawPrompt,
          };

      await sendMessageMutation.mutateAsync({
        taskId: currentTaskId,
        agentName,
        content,
      });
    },
    [
      taskID,
      agentName,
      createTaskMutation,
      updateParams,
      sendMessageMutation,
      taskParams,
    ]
  );

  const handleSendPrompt = useCallback(async () => {
    if (isDisabled || !prompt.trim() || !agentName) {
      toast.error('Please select an agent and enter a prompt');
      return;
    }

    if (isSendingJSON) {
      try {
        JSON.parse(prompt);
      } catch {
        toast.error('Invalid JSON');
        return;
      }
    }

    const text = prompt;
    const asJson = isSendingJSON;
    setPrompt('');
    await performSend(text, asJson);
  }, [isDisabled, prompt, agentName, isSendingJSON, setPrompt, performSend]);

  const handleEnqueue = useCallback(() => {
    if (!prompt.trim()) return;

    if (isSendingJSON) {
      try {
        JSON.parse(prompt);
      } catch {
        toast.error('Invalid JSON');
        return;
      }
    }

    setQueuedMessage({ text: prompt, isJson: isSendingJSON });
    setPrompt('');
  }, [prompt, isSendingJSON, setPrompt]);

  const handleInterrupt = useCallback(() => {
    if (!taskID || !agentName) return;
    sendMessageMutation.abortStream(taskID);
    interruptTurnMutation.mutate({
      taskId: taskID,
      agentName,
      reason: 'user_interrupt',
    });
  }, [taskID, agentName, sendMessageMutation, interruptTurnMutation]);

  const handleComposerSubmit = useCallback(() => {
    if (isStreaming) {
      handleEnqueue();
    } else {
      handleSendPrompt();
    }
  }, [isStreaming, handleEnqueue, handleSendPrompt]);

  useEffect(() => {
    if (wasStreamingRef.current && !isStreaming && queuedMessage) {
      const queued = queuedMessage;
      setQueuedMessage(null);
      performSend(queued.text, queued.isJson);
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming, queuedMessage, performSend]);

  useEffect(() => {
    if (!isStreaming) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleInterrupt();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isStreaming, handleInterrupt]);

  const isStopMode = isStreaming && !prompt.trim();
  const isPrimaryDisabled = isStopMode
    ? isDisabled
    : isDisabled || !prompt.trim();

  return (
    <div className="flex w-full max-w-3xl flex-col gap-2">
      {!taskID && !isDisabled && (
        <div className="flex flex-col gap-1">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground ml-4 flex items-center gap-1 text-sm transition-colors"
            onClick={() => setIsTaskParamsOpen(v => !v)}
          >
            <span>{isTaskParamsOpen ? '▾' : '▸'}</span>
            Task Parameters
          </button>
          {isTaskParamsOpen && (
            <DataInput
              prompt={taskParams}
              setPrompt={setTaskParams}
              isDisabled={isDisabled}
              handleSendPrompt={handleSendPrompt}
              codeMirrorViewRef={taskParamsViewRef}
            />
          )}
        </div>
      )}
      {queuedMessage && (
        <div className="border-input bg-muted/40 text-muted-foreground ml-4 flex max-w-full items-center gap-2 self-start rounded-full border py-1 pr-1 pl-3 text-sm">
          <span className="truncate">Queued: {queuedMessage.text}</span>
          <IconButton
            className="size-6 rounded-full"
            iconSize="sm"
            variant="ghost"
            onClick={() => setQueuedMessage(null)}
            icon={X}
            aria-label="Remove queued message"
          />
        </div>
      )}
      <div
        className={`border-input dark:bg-input ${isDisabled ? 'bg-muted scale-90 cursor-not-allowed' : 'scale-100'} flex w-full items-end justify-between rounded-4xl border py-2 pr-2 pl-6 shadow-sm transition-transform duration-300 disabled:cursor-not-allowed`}
      >
        {isSendingJSON ? (
          <DataInput
            prompt={prompt}
            setPrompt={setPrompt}
            isDisabled={isDisabled}
            handleSendPrompt={handleComposerSubmit}
            codeMirrorViewRef={codeMirrorViewRef}
          />
        ) : (
          <TextInput
            prompt={prompt}
            setPrompt={setPrompt}
            isDisabled={isDisabled}
            isTaskTerminal={isTaskTerminal}
            taskStatus={task?.status}
            handleSendPrompt={handleComposerSubmit}
            inputRef={textInputRef}
          />
        )}
        <IconButton
          className="pointer-events-auto size-10 rounded-full"
          onClick={isStopMode ? handleInterrupt : handleComposerSubmit}
          disabled={isPrimaryDisabled}
          icon={isStopMode ? Square : ArrowUp}
          aria-label={isStopMode ? 'Stop' : 'Send Prompt'}
        />
      </div>
      <div
        className="text-muted-foreground ml-4 flex items-center gap-2 rounded-full text-sm"
        style={{
          opacity: isDisabled ? 0 : 1,
          transition: 'opacity 0.2s',
        }}
      >
        Send JSON:
        <Switch
          checked={isSendingJSON}
          onCheckedChange={handleSetJson}
          aria-label="Send JSON"
        />
      </div>
    </div>
  );
}

// Cap the auto-grow height of the plain-text prompt textarea. Matches the
// JSON / CodeMirror branch's `maxHeight="200px"` so both variants feel
// consistent when authoring longer prompts.
const TEXT_INPUT_MAX_HEIGHT_PX = 200;

const TextInput = ({
  prompt,
  setPrompt,
  isDisabled,
  isTaskTerminal,
  taskStatus,
  handleSendPrompt,
  inputRef,
}: {
  prompt: string;
  setPrompt: (prompt: string) => void;
  isDisabled: boolean;
  isTaskTerminal: boolean;
  taskStatus: string | null | undefined;
  handleSendPrompt: () => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}) => {
  // Auto-resize the textarea height to fit content up to the max, then scroll
  // internally. Reset to 'auto' first so the height can shrink when the user
  // deletes lines, not just grow.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const next = Math.min(el.scrollHeight, TEXT_INPUT_MAX_HEIGHT_PX);
    el.style.height = `${next}px`;
    el.style.overflowY =
      el.scrollHeight > TEXT_INPUT_MAX_HEIGHT_PX ? 'auto' : 'hidden';
  }, [prompt, inputRef]);

  return (
    <textarea
      ref={inputRef}
      id="prompt-text-input"
      rows={1}
      value={prompt}
      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
        setPrompt(e.target.value)
      }
      onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        // Enter sends; Shift+Enter inserts a newline. Ignore Enter while an
        // IME composition is active so it can commit the candidate normally.
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
          e.preventDefault();
          if (!isDisabled && prompt.trim()) {
            handleSendPrompt();
          }
        }
      }}
      disabled={isDisabled}
      placeholder={
        isTaskTerminal
          ? `Task ${taskStatus?.toLowerCase() ?? 'ended'}`
          : isDisabled
            ? 'Select an agent to start'
            : 'Enter your prompt'
      }
      className="mr-2 flex-1 resize-none py-2 leading-6 outline-none focus:ring-0 focus:outline-none"
      style={{
        backgroundColor: 'inherit',
        cursor: 'inherit',
        maxHeight: `${TEXT_INPUT_MAX_HEIGHT_PX}px`,
      }}
    />
  );
};

const DataInput = ({
  prompt,
  setPrompt,
  isDisabled,
  handleSendPrompt,
  codeMirrorViewRef,
}: {
  prompt: string;
  setPrompt: (prompt: string) => void;
  isDisabled: boolean;
  handleSendPrompt: () => void;
  codeMirrorViewRef: React.MutableRefObject<EditorView | null>;
}) => {
  const commandEnterKeymap = useMemo(
    () =>
      Prec.highest(
        keymap.of([
          {
            key: 'Mod-Enter',
            run: () => {
              if (!isDisabled && prompt.trim()) {
                handleSendPrompt();
                return true;
              }
              return false;
            },
          },
        ])
      ),
    [isDisabled, prompt, handleSendPrompt]
  );

  return (
    <CodeMirror
      className="dark:bg-input/30 mx-1 w-full rounded-full text-sm"
      value={prompt}
      onChange={(value: string) => setPrompt(value)}
      onCreateEditor={view => {
        codeMirrorViewRef.current = view;
      }}
      extensions={[json(), noOutlineTheme, closeBrackets(), commandEnterKeymap]}
      placeholder='{ "message": "Enter JSON here..." }'
      basicSetup={{
        lineNumbers: false,
        foldGutter: false,
        highlightActiveLineGutter: false,
        highlightActiveLine: false,
      }}
      editable={!isDisabled}
      theme="none"
      maxHeight="200px"
    />
  );
};
