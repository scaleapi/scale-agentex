'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { closeBrackets } from '@codemirror/autocomplete';
import { json } from '@codemirror/lang-json';
import { Prec } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import CodeMirror from '@uiw/react-codemirror';
import { DataContent, TextContent } from 'agentex/resources';
import { ArrowUp } from 'lucide-react';

import { IconButton } from '@/components/agentex/icon-button';
import { toast } from '@/components/agentex/toast';
import { useAgentexClient } from '@/components/providers';
import { Switch } from '@/components/ui/switch';
import { useCreateTask } from '@/hooks/use-create-task';
import {
  SearchParamKey,
  useSafeSearchParams,
} from '@/hooks/use-safe-search-params';
import { useSendMessage } from '@/hooks/use-task-messages';

export type PromptInputProps = {
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
    backgroundColor: 'transparent',
  },
});

export function PromptInput({ prompt, setPrompt }: PromptInputProps) {
  const { taskID, agentName, updateParams } = useSafeSearchParams();
  const [isClient, setIsClient] = useState(false);
  const [isSendingJSON, setIsSendingJSON] = useState(false);

  const { agentexClient } = useAgentexClient();

  const createTaskMutation = useCreateTask({ agentexClient });
  const sendMessageMutation = useSendMessage({ agentexClient });

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

  const isDisabled = useMemo(
    () => !agentName || !isClient,
    [agentName, isClient]
  );

  const handleSendPrompt = useCallback(async () => {
    if (isDisabled || !prompt.trim() || !agentName) {
      toast.error('Please select an agent and enter a prompt');
      return;
    }

    let currentTaskId = taskID;
    const currentPrompt = prompt;

    if (isSendingJSON) {
      try {
        JSON.parse(prompt);
      } catch {
        toast.error('Invalid JSON');
        return;
      }
    }

    setPrompt('');

    if (!currentTaskId) {
      const task = await createTaskMutation.mutateAsync({
        agentName: agentName,
        params: {
          description: prompt,
          content: currentPrompt,
        },
      });
      currentTaskId = task.id;
      updateParams({ [SearchParamKey.TASK_ID]: currentTaskId });
    }

    const content: TextContent | DataContent = isSendingJSON
      ? {
          type: 'data',
          author: 'user',
          data: JSON.parse(prompt) as Record<string, unknown>,
        }
      : {
          type: 'text',
          author: 'user',
          format: 'plain',
          attachments: [],
          content: prompt as string,
        };

    await sendMessageMutation.mutateAsync({
      taskId: currentTaskId,
      agentName: agentName!,
      content,
    });
  }, [
    isDisabled,
    prompt,
    taskID,
    agentName,
    createTaskMutation,
    updateParams,
    sendMessageMutation,
    setPrompt,
    isSendingJSON,
  ]);

  return (
    <div className="flex w-full flex-col gap-2">
      <div
        className={`border-input dark:bg-input/30 ${isDisabled ? 'bg-muted scale-90 cursor-not-allowed' : 'scale-100'} flex w-full items-center justify-between rounded-4xl border py-2 pr-2 pl-6 transition-transform duration-300 disabled:cursor-not-allowed`}
      >
        {isSendingJSON ? (
          <DataInput
            prompt={prompt}
            setPrompt={setPrompt}
            isDisabled={isDisabled}
            handleSendPrompt={handleSendPrompt}
          />
        ) : (
          <TextInput
            prompt={prompt}
            setPrompt={setPrompt}
            isDisabled={isDisabled}
            handleSendPrompt={handleSendPrompt}
          />
        )}
        <IconButton
          className="pointer-events-auto size-10 rounded-full"
          onClick={handleSendPrompt}
          disabled={isDisabled || !prompt.trim()}
          icon={ArrowUp}
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
        <Switch checked={isSendingJSON} onCheckedChange={handleSetJson} />
      </div>
    </div>
  );
}

const TextInput = ({
  prompt,
  setPrompt,
  isDisabled,
  handleSendPrompt,
}: {
  prompt: string;
  setPrompt: (prompt: string) => void;
  isDisabled: boolean;
  handleSendPrompt: () => void;
}) => {
  return (
    <input
      id="prompt-text-input"
      type="text"
      value={prompt}
      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
        setPrompt(e.target.value)
      }
      onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && !isDisabled && prompt.trim()) {
          handleSendPrompt();
        }
      }}
      disabled={isDisabled}
      placeholder={
        isDisabled ? 'Select an agent to start' : 'Enter your prompt'
      }
      className="mr-2 flex-1 outline-none focus:ring-0 focus:outline-none"
      style={{
        backgroundColor: 'inherit',
        cursor: 'inherit',
      }}
    />
  );
};

const DataInput = ({
  prompt,
  setPrompt,
  isDisabled,
  handleSendPrompt,
}: {
  prompt: string;
  setPrompt: (prompt: string) => void;
  isDisabled: boolean;
  handleSendPrompt: () => void;
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
      className="mx-1 w-full rounded-full text-sm"
      value={prompt}
      onChange={(value: string) => setPrompt(value)}
      extensions={[json(), noOutlineTheme, closeBrackets(), commandEnterKeymap]}
      placeholder='{ "message": "Enter JSON here..." }'
      basicSetup={{
        lineNumbers: false,
        foldGutter: false,
        highlightActiveLineGutter: false,
        highlightActiveLine: false,
      }}
      editable={!isDisabled}
      maxHeight="200px"
      style={{
        backgroundColor: 'inherit',
        cursor: 'inherit',
      }}
    />
  );
};
