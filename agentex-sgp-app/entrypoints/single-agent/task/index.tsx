import { MemoizedTaskMessagesComponent } from '@/components/agentex/task-messages';
import {
  useAgentexTask,
  useAgentexTaskStore,
} from '@/hooks/use-agentex-task-store';
import { useSingleAgentTaskController } from './single-agent-task-controller';
import { TaskStatusBadge } from '@/components/agentex/task-status-badge';
import { TaskTopBar } from '@/components/agentex/task-top-bar';
import { useState, useEffect, useRef } from 'react';
import { useSafeTheme } from '@/hooks/use-safe-theme';

import {
  CreateUserMessageForm,
  CreateUserMessageFormContent,
} from '@/components/agentex/create-user-message-form';

export function Task() {
  const task = useAgentexTask();
  const messages = useAgentexTaskStore((s) => s.messages);
  const theme = useSafeTheme();
  const { isSendMessageEnabled, sendMessage } = useSingleAgentTaskController();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const isTaskTerminal = task?.status != null && task.status !== 'RUNNING';

  // Scroll to absolute bottom when task loads or changes
  useEffect(() => {
    if (scrollContainerRef.current && task?.id) {
      // Use a small delay to ensure content is rendered and heights are calculated
      setTimeout(() => {
        if (scrollContainerRef.current) {
          // Scroll to the maximum possible scroll position (includes blank space)
          scrollContainerRef.current.scrollTo({
            top: scrollContainerRef.current.scrollHeight,
            behavior: 'smooth',
          });
        }
      }, 150);
    }
  }, [task?.id]);

  return (
    <div className="flex flex-1 flex-col h-full bg-task-background">
      <TaskTopBar taskId={task?.id ?? null} />

      {/* Messages Area - Scrollable */}
      <div
        ref={scrollContainerRef}
        className="flex flex-col flex-1 overflow-y-auto items-center"
      >
        <MemoizedTaskMessagesComponent messages={messages} />
        {isTaskTerminal && (
          <div className="w-full max-w-[800px] px-4 mt-4">
            <TaskStatusBadge status={task?.status} size="lg" />
          </div>
        )}
      </div>

      {/* Form Area - Sticky Bottom */}
      <div className="max-w-[800px] mx-auto w-full p-4 mb-2">
        {errorMessage && (
          <div
            className="text-destructive mb-2"
            role="alert"
            aria-live="polite"
          >
            {errorMessage}
          </div>
        )}
        <CreateUserMessageForm
          agentOptions={[]}
          disabled={isSending || !isSendMessageEnabled}
          theme={theme}
          onSubmit={(data, resetForm) => {
            if (task === undefined) {
              return;
            }

            setErrorMessage(null);
            setIsSending(true);
            sendMessage(
              data.kind === 'data'
                ? {
                    author: 'user',
                    type: 'data',
                    data: data.content,
                  }
                : {
                    author: 'user',
                    type: 'text',
                    format: 'markdown',
                    content: data.content,
                  }
            ).then(
              () => {
                setIsSending(false);
                resetForm();
              },
              (error) => {
                setIsSending(false);
                console.error(error);

                const caughtErrorMessage: string | null =
                  typeof error === 'object' &&
                  error !== null &&
                  'message' in error &&
                  typeof error.message === 'string'
                    ? error.message
                    : null;

                setErrorMessage(
                  caughtErrorMessage ?? 'Failed to send message.'
                );
              }
            );
          }}
        >
          <CreateUserMessageFormContent />
        </CreateUserMessageForm>
      </div>
    </div>
  );
}
