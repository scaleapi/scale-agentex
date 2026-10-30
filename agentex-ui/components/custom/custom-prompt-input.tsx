'use client';

import { useCallback, useMemo, useRef } from 'react';

import { ArrowUp } from 'lucide-react';

import { useAgentexClient } from '@/components/providers';
import { IconButton } from '@/components/ui/icon-button';
import { toast } from '@/components/ui/toast';
import { useCreateTask } from '@/hooks/use-create-task';
import { useSendMessage } from '@/hooks/use-task-messages';
import { useTask } from '@/hooks/use-tasks';
import { TaskStatusEnum } from '@/lib/types';

import type { GoldenAgentConfig } from './config-panel';
import type { DataContent, TextContent } from 'agentex/resources';

const GOLDEN_AGENT_NAME = 'golden-agent';

type CustomPromptInputProps = {
  taskId: string | null;
  config: GoldenAgentConfig;
  prompt: string;
  setPrompt: (prompt: string) => void;
  onTaskCreated: (taskId: string) => void;
};

export function CustomPromptInput({
  taskId,
  config,
  prompt,
  setPrompt,
  onTaskCreated,
}: CustomPromptInputProps) {
  const { agentexClient } = useAgentexClient();
  const createTaskMutation = useCreateTask({ agentexClient });
  const sendMessageMutation = useSendMessage({ agentexClient });
  const { data: task } = useTask({
    agentexClient,
    taskId: taskId ?? '',
  });
  const inputRef = useRef<HTMLInputElement>(null);

  const isTaskTerminal = useMemo(() => {
    if (!taskId || !task) return false;
    return task.status != null && task.status !== TaskStatusEnum.RUNNING;
  }, [taskId, task]);

  const isDisabled = isTaskTerminal;

  const handleSendPrompt = useCallback(async () => {
    if (!prompt.trim()) {
      toast.error('Please enter a prompt');
      return;
    }

    const currentPrompt = prompt;
    setPrompt('');

    let currentTaskId = taskId;

    if (!currentTaskId) {
      const params: Record<string, unknown> = {
        system_prompt: config.system_prompt || null,
        allowed_tools: config.allowed_tools,
        harness: config.harness,
        model: config.model,
      };

      const createdTask = await createTaskMutation.mutateAsync({
        agentName: GOLDEN_AGENT_NAME,
        params,
      });
      currentTaskId = createdTask.id;
      onTaskCreated(currentTaskId);

      const content: DataContent = {
        type: 'data',
        author: 'user',
        data: {
          system_prompt: config.system_prompt || null,
          allowed_tools: config.allowed_tools,
          harness: config.harness,
          model: config.model,
          message: currentPrompt,
        },
      };

      await sendMessageMutation.mutateAsync({
        taskId: currentTaskId,
        agentName: GOLDEN_AGENT_NAME,
        content,
      });
    } else {
      const content: TextContent = {
        type: 'text',
        author: 'user',
        format: 'plain',
        attachments: [],
        content: currentPrompt,
      };

      await sendMessageMutation.mutateAsync({
        taskId: currentTaskId,
        agentName: GOLDEN_AGENT_NAME,
        content,
      });
    }
  }, [
    prompt,
    taskId,
    config,
    setPrompt,
    createTaskMutation,
    sendMessageMutation,
    onTaskCreated,
  ]);

  return (
    <div className="flex w-full max-w-3xl flex-col gap-2">
      <div
        className={`border-input dark:bg-input ${isDisabled ? 'bg-muted scale-90 cursor-not-allowed' : 'scale-100'} flex w-full items-center justify-between rounded-4xl border py-2 pr-2 pl-6 shadow-sm transition-transform duration-300`}
      >
        <input
          ref={inputRef}
          type="text"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !isDisabled && prompt.trim()) {
              handleSendPrompt();
            }
          }}
          disabled={isDisabled}
          placeholder={
            isTaskTerminal
              ? `Task ${task?.status?.toLowerCase() ?? 'ended'}`
              : 'Enter your prompt'
          }
          className="mr-2 flex-1 outline-none focus:ring-0 focus:outline-none"
          style={{ backgroundColor: 'inherit', cursor: 'inherit' }}
        />
        <IconButton
          className="pointer-events-auto size-10 rounded-full"
          onClick={handleSendPrompt}
          disabled={isDisabled || !prompt.trim()}
          icon={ArrowUp}
          aria-label="Send Prompt"
        />
      </div>
    </div>
  );
}
